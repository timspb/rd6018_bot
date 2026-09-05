"""Authoritative programmed-readback B16 gate for the physical-test plane.

The original B16 bench hook exposed a real production integration defect: writable
ESPHome ``number`` entities do not provide an authoritative heartbeat when a same-value
write leaves their state unchanged.  V2 therefore reads programmed V/I/OVP/OCP from
separate force-updated, read-only Modbus sensors while retaining the existing numbers
as actuator endpoints.

This extension deliberately shadows only the existing B16 operation on the same
root-only AF_UNIX server.  It accepts no values/entities/timestamps and never creates
another listener.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from physical_test_control import PhysicalTestControl, PhysicalTestControlError, _json_value
from rd6018_telemetry import (
    ProtectionStatus,
    finite_float,
    resolve_protection,
    telemetry_freshness,
)
from safe_output import OutputRequest, SafetySupervisor, snapshot_from_live


OPERATION = "b16_fault_hold_stale_set_voltage_readback"
_STALE_TIMESTAMP = "2000-01-01T00:00:00+00:00"
_B16_REAL_READBACK_PROOF_TIMEOUT_S = 15.0
_B16_REAL_READBACK_PROOF_POLL_S = 0.25
_EXPECTED_READBACK_SOURCES = {
    "set_voltage": "set_voltage_readback_v2",
    "set_current": "set_current_readback_v2",
    "ovp": "ovp_readback_v2",
    "ocp": "ocp_readback_v2",
}


def _timestamp_epoch(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


class PhysicalTestControlProgrammedReadbackV2:
    """B16 gate backed by force-updated read-only RD register mirrors."""

    def __init__(self, app: Any, control: PhysicalTestControl) -> None:
        self.app = app
        self.control = control
        self._original_dispatch = control.dispatch

    @staticmethod
    def _inactive(obj: Any) -> bool:
        return not bool(getattr(obj, "active", False)) and not bool(
            getattr(obj, "is_active", False)
        ) and not bool(getattr(obj, "off_pending", False))

    @staticmethod
    def _programmed_values(live: Dict[str, Any]) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for key in _EXPECTED_READBACK_SOURCES:
            value = finite_float(live.get(key))
            if value is None:
                raise PhysicalTestControlError(
                    f"B16 requires numeric authoritative programmed readback for {key}"
                )
            values[key] = float(value)
        return values

    @staticmethod
    def _require_readback_source(live: Dict[str, Any], key: str) -> Dict[str, Any]:
        meta = live.get("_meta")
        if not isinstance(meta, dict):
            raise PhysicalTestControlError("B16 requires runtime freshness metadata")
        entry = meta.get(key)
        expected = _EXPECTED_READBACK_SOURCES[key]
        if not isinstance(entry, dict) or entry.get("source_key") != expected:
            raise PhysicalTestControlError(
                f"B16 requires canonical {key} source_key={expected}"
            )
        if str(entry.get("status") or "ok").lower() != "ok":
            raise PhysicalTestControlError(
                f"B16 requires healthy canonical {key} readback metadata"
            )
        freshness = telemetry_freshness(live, [key])
        if not freshness.valid:
            raise PhysicalTestControlError(
                f"B16 requires fresh canonical {key} readback before injection: {freshness.detail}"
            )
        if _timestamp_epoch(entry.get("last_reported") or entry.get("last_updated")) is None:
            raise PhysicalTestControlError(
                f"B16 requires timestamped canonical {key} readback heartbeat"
            )
        return dict(entry)

    @staticmethod
    def _same_programmed_values(
        expected: Dict[str, float], live: Dict[str, Any], tolerance: float
    ) -> bool:
        for key, value in expected.items():
            observed = finite_float(live.get(key))
            if observed is None or abs(float(observed) - value) > tolerance:
                return False
        return True

    @staticmethod
    def _stale_set_voltage_meta(live: Dict[str, Any]) -> Dict[str, Any]:
        meta = live.get("_meta")
        if not isinstance(meta, dict):
            raise PhysicalTestControlError("B16 injected readback lost runtime metadata")
        entry = meta.get("set_voltage")
        expected = _EXPECTED_READBACK_SOURCES["set_voltage"]
        if not isinstance(entry, dict) or entry.get("source_key") != expected:
            raise PhysicalTestControlError(
                f"B16 injected readback lost canonical set_voltage source_key={expected}"
            )
        mutated = dict(live)
        copied_meta: Dict[str, Any] = {}
        for key, value in meta.items():
            copied_meta[key] = dict(value) if isinstance(value, dict) else value
        stale = dict(entry)
        stale["last_reported"] = _STALE_TIMESTAMP
        stale["last_updated"] = _STALE_TIMESTAMP
        stale["age_s"] = 1_000_000_000.0
        copied_meta["set_voltage"] = stale
        mutated["_meta"] = copied_meta
        return mutated

    async def run(self) -> Dict[str, Any]:
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "pb_managed", False)):
            raise PhysicalTestControlError("B16 programmed-readback test requires PB_MANAGED")
        if bool(getattr(manager, "release_in_progress", False)):
            raise PhysicalTestControlError("B16 rejected during control-mode transfer")
        for name in (
            "charge_controller",
            "manual_session_manager",
            "rd_managed_live_adoption",
            "rd_managed_mix_adoption",
        ):
            if not self._inactive(getattr(self.app, name, None)):
                raise PhysicalTestControlError(
                    f"B16 requires no active managed authority ({name})"
                )

        guard = getattr(self.app, "runtime_safety_guard", None)
        original_raw = getattr(guard, "_raw_live", None)
        if not callable(original_raw):
            raise PhysicalTestControlError("B16 raw safety reader unavailable")
        if bool(getattr(guard, "_off_unconfirmed", False)):
            raise PhysicalTestControlError(
                "B16 blocked while a previous Output OFF remains unconfirmed"
            )

        live_before = await original_raw()
        if not self.control._is_off(live_before):
            raise PhysicalTestControlError("B16 requires positively confirmed Output OFF")
        if resolve_protection(live_before).status is not ProtectionStatus.NORMAL:
            raise PhysicalTestControlError("B16 requires normal hardware protection state")
        lease_before = await self.control._lease_state()
        if (
            bool(lease_before.armed)
            or bool(lease_before.tripped)
            or bool(lease_before.boot_quarantine)
        ):
            raise PhysicalTestControlError(
                "B16 requires unarmed/untripped edge lease with quarantine clear"
            )

        programmed = self._programmed_values(live_before)
        source_meta = {
            key: self._require_readback_source(live_before, key)
            for key in _EXPECTED_READBACK_SOURCES
        }
        baseline_vset_meta = source_meta["set_voltage"]
        baseline_vset_ts = _timestamp_epoch(
            baseline_vset_meta.get("last_reported")
            or baseline_vset_meta.get("last_updated")
        )
        assert baseline_vset_ts is not None

        snapshot = snapshot_from_live(live_before, require_programming_freshness=False)
        if snapshot is None:
            raise PhysicalTestControlError("B16 normal idle preflight rejected")
        request = OutputRequest(
            voltage_v=programmed["set_voltage"],
            current_a=programmed["set_current"],
            ovp_v=programmed["ovp"],
            ocp_a=programmed["ocp"],
            recipe_voltage_ceiling_v=programmed["set_voltage"],
        )
        decision = SafetySupervisor().preflight(request, snapshot)
        if not decision.allowed:
            raise PhysicalTestControlError(
                f"B16 same-value transaction is not safe: {decision.detail}"
            )

        adapter = self.app.hass
        safe_enable = getattr(adapter, "safe_enable_output", None)
        original_get_all_live = getattr(adapter, "get_all_live", None)
        original_set_ovp = getattr(adapter, "set_ovp", None)
        original_set_ocp = getattr(adapter, "set_ocp", None)
        original_set_voltage = getattr(adapter, "set_voltage", None)
        original_set_current = getattr(adapter, "set_current", None)
        original_turn_on = getattr(adapter, "turn_on", None)
        original_turn_off = getattr(adapter, "turn_off", None)
        if not all(
            callable(item)
            for item in (
                safe_enable,
                original_get_all_live,
                original_set_ovp,
                original_set_ocp,
                original_set_voltage,
                original_set_current,
                original_turn_on,
                original_turn_off,
            )
        ):
            raise PhysicalTestControlError("B16 production actuator boundary is incomplete")

        injection_task = asyncio.current_task()
        counts = {
            "ovp": 0,
            "ocp": 0,
            "set_voltage": 0,
            "set_current": 0,
            "turn_on": 0,
            "turn_off": 0,
        }
        injected_readback = False

        async def injected_get_all_live() -> Dict[str, Any]:
            nonlocal injected_readback
            live = await original_get_all_live()
            if asyncio.current_task() is not injection_task or counts["set_voltage"] < 1:
                return live
            injected_readback = True
            return self._stale_set_voltage_meta(live)

        def same_value_wrapper(
            key: str, expected: float, original: Callable[[float], Any]
        ) -> Callable[[float], Any]:
            async def wrapped(value: float) -> bool:
                if asyncio.current_task() is injection_task:
                    parsed = finite_float(value)
                    if parsed is None or abs(float(parsed) - expected) > 1e-9:
                        raise PhysicalTestControlError(
                            f"B16 blocked unexpected {key} write {value!r}; expected {expected}"
                        )
                    counts[key] += 1
                return bool(await original(value))

            return wrapped

        async def blocked_turn_on(entity_id: Optional[str] = None) -> bool:
            if asyncio.current_task() is injection_task:
                counts["turn_on"] += 1
                raise PhysicalTestControlError(
                    "B16 coordinator attempted Output ON before fresh programmed readback"
                )
            return bool(await original_turn_on(entity_id))

        async def counted_turn_off(entity_id: Optional[str] = None) -> bool:
            if asyncio.current_task() is injection_task:
                counts["turn_off"] += 1
            return bool(await original_turn_off(entity_id))

        adapter.get_all_live = injected_get_all_live
        adapter.set_ovp = same_value_wrapper("ovp", programmed["ovp"], original_set_ovp)
        adapter.set_ocp = same_value_wrapper("ocp", programmed["ocp"], original_set_ocp)
        adapter.set_voltage = same_value_wrapper(
            "set_voltage", programmed["set_voltage"], original_set_voltage
        )
        adapter.set_current = same_value_wrapper(
            "set_current", programmed["set_current"], original_set_current
        )
        adapter.turn_on = blocked_turn_on
        adapter.turn_off = counted_turn_off

        result = None
        caught: Optional[Exception] = None
        try:
            try:
                result = await safe_enable(
                    voltage_v=programmed["set_voltage"],
                    current_a=programmed["set_current"],
                    ovp_v=programmed["ovp"],
                    ocp_a=programmed["ocp"],
                    recipe_voltage_ceiling_v=programmed["set_voltage"],
                )
            except Exception as exc:
                caught = exc
        finally:
            adapter.get_all_live = original_get_all_live
            adapter.set_ovp = original_set_ovp
            adapter.set_ocp = original_set_ocp
            adapter.set_voltage = original_set_voltage
            adapter.set_current = original_set_current
            adapter.turn_on = original_turn_on
            adapter.turn_off = original_turn_off

        if caught is not None:
            raise PhysicalTestControlError(
                f"B16 safe-output path raised unexpectedly: {type(caught).__name__}: {caught}"
            ) from caught
        if result is None:
            raise PhysicalTestControlError("B16 safe-output path returned no result")
        if counts["turn_on"] != 0:
            raise PhysicalTestControlError(
                "B16 failed: coordinator reached Output ON before fresh programmed readback"
            )
        if not injected_readback:
            raise PhysicalTestControlError("B16 did not reach programmed-readback boundary")
        for key in ("ovp", "ocp", "set_voltage", "set_current"):
            if counts[key] != 1:
                raise PhysicalTestControlError(
                    f"B16 expected exactly one same-value {key} write, observed {counts[key]}"
                )
        if counts["turn_off"] != 1:
            raise PhysicalTestControlError(
                f"B16 expected one fail-safe Output OFF request, observed {counts['turn_off']}"
            )
        if bool(getattr(result, "enabled", False)):
            raise PhysicalTestControlError("B16 stale readback was accepted")
        violation_values = {
            str(getattr(value, "value", value))
            for value in getattr(result, "violations", frozenset())
        }
        detail = str(getattr(result, "detail", "") or "")
        if "telemetry_invalid" not in violation_values or (
            "programmed readback telemetry missing/invalid" not in detail
        ):
            raise PhysicalTestControlError(
                f"B16 failed at unexpected boundary: violations={sorted(violation_values)} detail={detail}"
            )
        if "output_off_unconfirmed" in violation_values:
            raise PhysicalTestControlError(
                "B16 Output OFF confirmation failed; stop physical testing and investigate"
            )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + _B16_REAL_READBACK_PROOF_TIMEOUT_S
        real_after: Optional[Dict[str, Any]] = None
        real_vset_meta: Optional[Dict[str, Any]] = None
        heartbeat_advanced = False
        while True:
            real_after = await original_get_all_live()
            try:
                candidate = self._require_readback_source(real_after, "set_voltage")
            except PhysicalTestControlError:
                candidate = None
            if candidate is not None:
                candidate_ts = _timestamp_epoch(
                    candidate.get("last_reported") or candidate.get("last_updated")
                )
                if candidate_ts is not None and candidate_ts > baseline_vset_ts:
                    real_vset_meta = candidate
                    heartbeat_advanced = True
                    break
            remaining = deadline - loop.time()
            if remaining <= 0.0:
                raise PhysicalTestControlError(
                    "B16 authoritative set_voltage_readback_v2 heartbeat did not advance after programming"
                )
            await asyncio.sleep(min(_B16_REAL_READBACK_PROOF_POLL_S, remaining))

        assert real_after is not None and real_vset_meta is not None
        for key in _EXPECTED_READBACK_SOURCES:
            self._require_readback_source(real_after, key)
        live_after = await original_raw()
        lease_after = await self.control._lease_state()
        if not self.control._is_off(live_after):
            raise PhysicalTestControlError("B16 did not finish with canonical Output OFF")
        if bool(lease_after.armed):
            raise PhysicalTestControlError("B16 armed edge lease despite no Output ON attempt")
        tolerance = float(getattr(guard, "READBACK_TOLERANCE", 0.08))
        if not self._same_programmed_values(programmed, live_after, tolerance):
            raise PhysicalTestControlError("B16 changed the programmed envelope")

        return {
            "fault": OPERATION,
            "blocked_before_output_on": True,
            "detail": detail,
            "violations": sorted(violation_values),
            "programmed_values": dict(programmed),
            "programming_writes": {
                "ovp": counts["ovp"],
                "ocp": counts["ocp"],
                "set_voltage": counts["set_voltage"],
                "set_current": counts["set_current"],
            },
            "output_on_attempts": counts["turn_on"],
            "output_off_attempts": counts["turn_off"],
            "output": live_after.get("switch"),
            "output_state_code_v2": live_after.get("output_state_code_v2"),
            "lease_armed": lease_after.armed,
            "remaining_s": lease_after.remaining_s,
            "generation_before": lease_before.generation,
            "generation_after": lease_after.generation,
            "set_voltage_source_key": real_vset_meta.get("source_key"),
            "set_voltage_last_reported_before": baseline_vset_meta.get("last_reported"),
            "set_voltage_last_reported_after": real_vset_meta.get("last_reported"),
            "set_voltage_heartbeat_advanced": heartbeat_advanced,
            "hardware_value_changes_expected": 0,
        }

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict) or request.get("op") != OPERATION:
            return await self._original_dispatch(request)
        try:
            async with self.control._operation_lock:
                self.control._require_fields(request, {"op"})
                result = await self.run()
            return {"ok": True, "operation": OPERATION, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self.control._error(str(exc))
        except Exception as exc:
            return self.control._error(f"operation rejected: {type(exc).__name__}: {exc}")


def install_physical_test_control_programmed_readback_v2(
    app: Any, control: PhysicalTestControl
) -> PhysicalTestControlProgrammedReadbackV2:
    """Shadow only B16 on the existing AF_UNIX physical-test control plane."""
    existing = getattr(app, "physical_test_control_programmed_readback_v2", None)
    if isinstance(existing, PhysicalTestControlProgrammedReadbackV2):
        return existing
    extension = PhysicalTestControlProgrammedReadbackV2(app, control)
    control.dispatch = extension.dispatch
    app.physical_test_control_programmed_readback_v2 = extension
    return extension
