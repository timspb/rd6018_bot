"""Deterministic source-freshness faults for the local physical-test control plane.

This extension reuses the existing opt-in root-only AF_UNIX server.  Managed-source
operations mutate exactly one in-memory production decision snapshot, never HA/RD
state.  B16 performs one deliberately narrow same-value OVP/OCP/V/I programming
transaction while Output is already OFF and withholds only the post-write Vset
freshness observation from the production coordinator.  No operation accepts an
entity ID, timestamp, setpoint, or other authority-widening parameter.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from physical_test_control import (
    PhysicalTestControl,
    PhysicalTestControlError,
    _json_value,
)
from rd6018_telemetry import (
    ProtectionStatus,
    RegulationMode,
    as_bool,
    finite_float,
    resolve_protection,
    resolve_regulation,
    telemetry_freshness,
)
from safe_output import OutputRequest, SafetySupervisor, snapshot_from_live


_SOURCE_FAULT_OPS = {
    "d061_fault_stale_temp_source",
    "d061_fault_stale_output_source",
    "d061_fault_stale_vout_source",
    "d061_fault_missing_runtime_meta",
    "d062_fault_stale_regulation_source",
}
_PROGRAMMED_READBACK_OPS = {
    "b16_fault_hold_stale_set_voltage_readback",
}
_STALE_TIMESTAMP = "2000-01-01T00:00:00+00:00"
_B16_REAL_READBACK_PROOF_TIMEOUT_S = 8.0
_B16_REAL_READBACK_PROOF_POLL_S = 0.25


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


class PhysicalTestControlSourceFaults:
    """One-shot source-evidence faults composed over the existing control server."""

    def __init__(self, app: Any, control: PhysicalTestControl) -> None:
        self.app = app
        self.control = control
        self._original_dispatch = control.dispatch

    @staticmethod
    def _copy_live_with_meta(live: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        meta = live.get("_meta")
        if not isinstance(meta, dict):
            raise PhysicalTestControlError(
                "source-fault injection requires existing runtime freshness metadata"
            )
        mutated = dict(live)
        copied_meta: Dict[str, Any] = {}
        for key, value in meta.items():
            copied_meta[key] = dict(value) if isinstance(value, dict) else value
        mutated["_meta"] = copied_meta
        return mutated, copied_meta

    @staticmethod
    def _stale_entry(
        meta: Dict[str, Any],
        key: str,
        *,
        expected_source_key: Optional[str] = None,
    ) -> None:
        entry = meta.get(key)
        if not isinstance(entry, dict):
            raise PhysicalTestControlError(
                f"source-fault injection requires freshness metadata for {key}"
            )
        if expected_source_key is not None and entry.get("source_key") != expected_source_key:
            raise PhysicalTestControlError(
                f"source-fault injection expected {key} source_key={expected_source_key}"
            )
        stale = dict(entry)
        stale["last_reported"] = _STALE_TIMESTAMP
        stale["last_updated"] = _STALE_TIMESTAMP
        stale["age_s"] = 1_000_000_000.0
        meta[key] = stale

    def _stale_single(
        self,
        live: Dict[str, Any],
        key: str,
        *,
        expected_source_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        mutated, meta = self._copy_live_with_meta(live)
        self._stale_entry(meta, key, expected_source_key=expected_source_key)
        return mutated

    def _missing_meta(self, live: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(live.get("_meta"), dict):
            raise PhysicalTestControlError(
                "runtime metadata is already unavailable before fault injection"
            )
        mutated = dict(live)
        mutated.pop("_meta", None)
        return mutated

    def _stale_regulation(self, live: Dict[str, Any]) -> Dict[str, Any]:
        regulation = resolve_regulation(live)
        if regulation not in {RegulationMode.CV, RegulationMode.CC}:
            raise PhysicalTestControlError(
                "regulation-source fault requires authoritative CV/CC regulation_code"
            )
        expected_cv = regulation is RegulationMode.CV
        expected_cc = regulation is RegulationMode.CC
        if as_bool(live.get("is_cv")) is not expected_cv or as_bool(live.get("is_cc")) is not expected_cc:
            raise PhysicalTestControlError(
                "canonical is_cv/is_cc values are incoherent with regulation_code"
            )

        mutated, meta = self._copy_live_with_meta(live)
        regulation_meta = meta.get("regulation_code")
        if not isinstance(regulation_meta, dict):
            raise PhysicalTestControlError(
                "regulation-source fault requires regulation_code freshness metadata"
            )
        for derived in ("is_cv", "is_cc"):
            entry = meta.get(derived)
            if not isinstance(entry, dict) or entry.get("source_key") != "regulation_code":
                raise PhysicalTestControlError(
                    f"canonical {derived} metadata is not derived from regulation_code"
                )

        self._stale_entry(meta, "regulation_code")
        stale_regulation = dict(meta["regulation_code"])
        stale_regulation["source_key"] = "regulation_code"
        for derived in ("is_cv", "is_cc"):
            meta[derived] = dict(stale_regulation)
        return mutated

    async def _run_fault(
        self,
        *,
        operation: str,
        coordinator: Any,
        mutate: Callable[[Dict[str, Any]], Dict[str, Any]],
        expected_reason_fragment: str,
        authority_name: str,
    ) -> Dict[str, Any]:
        if coordinator is None or not bool(getattr(coordinator, "active", False)):
            raise PhysicalTestControlError(
                f"{operation} requires active {authority_name} authority"
            )

        guard = getattr(coordinator, "guard", None)
        original_raw = getattr(guard, "_raw_live", None)
        observe_once = getattr(coordinator, "observe_once", None)
        if not callable(original_raw) or not callable(observe_once):
            raise PhysicalTestControlError(
                f"{operation} production observation boundary is unavailable"
            )

        live_before = await original_raw()
        if not self.control._is_on(live_before):
            raise PhysicalTestControlError(f"{operation} requires positively confirmed Output ON")

        # Validate the intended source boundary before patching anything.
        mutate(live_before)

        before = await self.control._lease_state()
        injection_task = asyncio.current_task()
        consumed = False

        async def injected_raw_live() -> Dict[str, Any]:
            nonlocal consumed
            live = await original_raw()
            if asyncio.current_task() is not injection_task or consumed:
                return live
            consumed = True
            return mutate(live)

        guard._raw_live = injected_raw_live
        caught: Optional[Exception] = None
        try:
            try:
                await observe_once()
            except Exception as exc:
                caught = exc
        finally:
            guard._raw_live = original_raw

        if not consumed:
            raise PhysicalTestControlError(
                f"{operation} did not reach the production decision read"
            )
        if caught is None:
            raise PhysicalTestControlError(
                f"{operation} did not trip production fail-close"
            )
        reason = f"{type(caught).__name__}: {caught}"
        if expected_reason_fragment not in str(caught):
            raise PhysicalTestControlError(
                f"{operation} tripped an unexpected boundary: {reason}"
            ) from caught

        # The injected snapshot is gone before this point. If the safety guard forced
        # physical OFF, the real coordinator must now consume that real OFF transition
        # and retire/disarm its managed authority.
        if bool(getattr(coordinator, "active", False)) or bool(
            getattr(coordinator, "off_pending", False)
        ):
            await observe_once()

        live_after = await original_raw()
        after = await self.control._lease_state()
        if not self.control._is_off(live_after):
            raise PhysicalTestControlError(
                f"{operation} did not complete verified Output OFF"
            )
        if bool(after.armed):
            raise PhysicalTestControlError(
                f"{operation} left edge lease armed after confirmed Output OFF"
            )

        return {
            "fault": operation,
            "contained": True,
            "reason": reason,
            "generation_before": before.generation,
            "generation_after": after.generation,
            "output": live_after.get("switch"),
            "output_state_code_v2": live_after.get("output_state_code_v2"),
            "lease_armed": after.armed,
            "remaining_s": after.remaining_s,
            "state": _enum_value(getattr(coordinator, "state", None)),
            "terminal_reason": str(getattr(coordinator, "terminal_reason", "") or ""),
            "last_status": str(getattr(coordinator, "last_status", "") or ""),
            "hardware_writes_injected": 0,
        }

    @staticmethod
    def _inactive(obj: Any) -> bool:
        return not bool(getattr(obj, "active", False)) and not bool(
            getattr(obj, "is_active", False)
        ) and not bool(getattr(obj, "off_pending", False))

    @staticmethod
    def _programmed_values(live: Dict[str, Any]) -> Dict[str, float]:
        mapping = {
            "set_voltage": "set_voltage",
            "set_current": "set_current",
            "ovp": "ovp",
            "ocp": "ocp",
        }
        values: Dict[str, float] = {}
        for name, key in mapping.items():
            value = finite_float(live.get(key))
            if value is None:
                raise PhysicalTestControlError(
                    f"B16 requires numeric programmed readback for {key}"
                )
            values[name] = float(value)
        return values

    @staticmethod
    def _same_programmed_values(
        before: Dict[str, float],
        live: Dict[str, Any],
        tolerance: float,
    ) -> bool:
        for key, expected in before.items():
            observed = finite_float(live.get(key))
            if observed is None or abs(float(observed) - expected) > tolerance:
                return False
        return True

    async def b16_hold_stale_set_voltage_readback(self) -> Dict[str, Any]:
        """Prove fresh programmed readback is required before any Output ON attempt.

        Preconditions intentionally require a PB-managed but idle, positively-OFF
        system and an already stale idle Vset heartbeat. The operation reprograms the
        *same* OVP/OCP/V/I values and withholds only that old Vset metadata from the
        coordinator after the Vset write. Any attempt to change a value or reach
        Output ON is blocked by the harness before hardware actuation.
        """

        operation = "b16_fault_hold_stale_set_voltage_readback"
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "pb_managed", False)):
            raise PhysicalTestControlError(
                "B16 programmed-readback test requires PB_MANAGED"
            )
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
            raise PhysicalTestControlError(
                "B16 requires positively confirmed Output OFF before programming"
            )
        if resolve_protection(live_before).status is not ProtectionStatus.NORMAL:
            raise PhysicalTestControlError("B16 requires normal hardware protection state")

        lease_before = await self.control._lease_state()
        if bool(lease_before.armed) or bool(lease_before.tripped) or bool(
            lease_before.boot_quarantine
        ):
            raise PhysicalTestControlError(
                "B16 requires an unarmed, untripped edge lease with quarantine clear"
            )

        programmed = self._programmed_values(live_before)
        held_meta = live_before.get("_meta", {}).get("set_voltage")
        if not isinstance(held_meta, dict) or str(held_meta.get("status") or "ok").lower() != "ok":
            raise PhysicalTestControlError(
                "B16 requires existing healthy metadata for the idle set_voltage source"
            )
        idle_freshness = telemetry_freshness(live_before, ["set_voltage"])
        if idle_freshness.valid:
            raise PhysicalTestControlError(
                "B16 requires an already stale idle set_voltage heartbeat before the new write"
            )
        if "set_voltage stale" not in idle_freshness.detail:
            raise PhysicalTestControlError(
                f"B16 idle set_voltage evidence is invalid for the wrong reason: {idle_freshness.detail}"
            )
        held_meta = dict(held_meta)

        snapshot = snapshot_from_live(
            live_before,
            require_programming_freshness=False,
        )
        if snapshot is None:
            raise PhysicalTestControlError(
                "B16 normal idle preflight rejected before programmed-readback gating"
            )
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
        if not callable(safe_enable):
            raise PhysicalTestControlError("B16 safe-output coordinator API unavailable")

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
            if (
                asyncio.current_task() is not injection_task
                or counts["set_voltage"] < 1
            ):
                return live
            mutated, meta = self._copy_live_with_meta(live)
            meta["set_voltage"] = dict(held_meta)
            injected_readback = True
            return mutated

        def same_value_wrapper(
            key: str,
            expected: float,
            original: Callable[[float], Any],
        ) -> Callable[[float], Any]:
            async def wrapped(value: float) -> bool:
                if asyncio.current_task() is injection_task:
                    parsed = finite_float(value)
                    if parsed is None or abs(float(parsed) - expected) > 1e-9:
                        raise PhysicalTestControlError(
                            f"B16 blocked unexpected {key} write {value!r}; expected same value {expected}"
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
        if not injected_readback:
            raise PhysicalTestControlError(
                "B16 did not reach the post-programming readback boundary"
            )
        for key in ("ovp", "ocp", "set_voltage", "set_current"):
            if counts[key] != 1:
                raise PhysicalTestControlError(
                    f"B16 expected exactly one same-value {key} write, observed {counts[key]}"
                )
        if counts["turn_on"] != 0:
            raise PhysicalTestControlError(
                "B16 failed: coordinator reached Output ON before fresh programmed readback"
            )
        if counts["turn_off"] != 1:
            raise PhysicalTestControlError(
                f"B16 expected one fail-safe Output OFF request, observed {counts['turn_off']}"
            )
        if bool(getattr(result, "enabled", False)):
            raise PhysicalTestControlError(
                "B16 failed: stale programmed readback was accepted as an enabled output"
            )
        violation_values = {
            str(getattr(value, "value", value))
            for value in getattr(result, "violations", frozenset())
        }
        detail = str(getattr(result, "detail", "") or "")
        if "telemetry_invalid" not in violation_values or (
            "programmed readback telemetry missing/invalid" not in detail
        ):
            raise PhysicalTestControlError(
                f"B16 failed at an unexpected boundary: violations={sorted(violation_values)} detail={detail}"
            )
        if "output_off_unconfirmed" in violation_values:
            raise PhysicalTestControlError(
                "B16 Output OFF confirmation failed; stop physical testing and investigate"
            )

        # The public reader and every actuator method are restored before this proof.
        # A real fresh Vset heartbeat must now be visible, showing that the failed
        # coordinator read was caused by the one-shot holdback rather than HA failing
        # to observe the write at all.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _B16_REAL_READBACK_PROOF_TIMEOUT_S
        real_after: Optional[Dict[str, Any]] = None
        real_freshness = None
        while True:
            real_after = await original_get_all_live()
            real_freshness = telemetry_freshness(real_after, ["set_voltage"])
            if real_freshness.valid:
                break
            remaining = deadline - loop.time()
            if remaining <= 0.0:
                raise PhysicalTestControlError(
                    "B16 real set_voltage heartbeat did not become fresh after the write; injection is unproven"
                )
            await asyncio.sleep(min(_B16_REAL_READBACK_PROOF_POLL_S, remaining))

        live_after = await original_raw()
        lease_after = await self.control._lease_state()
        if not self.control._is_off(live_after):
            raise PhysicalTestControlError("B16 did not finish with canonical Output OFF")
        if bool(lease_after.armed):
            raise PhysicalTestControlError("B16 armed the edge lease despite no Output ON attempt")
        tolerance = float(getattr(guard, "READBACK_TOLERANCE", 0.08))
        if not self._same_programmed_values(programmed, live_after, tolerance):
            raise PhysicalTestControlError(
                "B16 same-value programming transaction changed the programmed envelope"
            )

        real_meta = real_after.get("_meta", {}).get("set_voltage", {}) if real_after else {}
        return {
            "fault": operation,
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
            "held_set_voltage_last_reported": held_meta.get("last_reported"),
            "real_set_voltage_last_reported_after": (
                real_meta.get("last_reported") if isinstance(real_meta, dict) else None
            ),
            "real_set_voltage_fresh_after": bool(real_freshness and real_freshness.valid),
            "hardware_value_changes_expected": 0,
        }

    async def d061_stale_temp(self) -> Dict[str, Any]:
        return await self._run_fault(
            operation="d061_fault_stale_temp_source",
            coordinator=getattr(self.app, "rd_managed_live_adoption", None),
            mutate=lambda live: self._stale_single(
                live, "temp_ext", expected_source_key="temp_ext_v2"
            ),
            expected_reason_fragment="temp_ext stale",
            authority_name="D061 adopted Manual",
        )

    async def d061_stale_output(self) -> Dict[str, Any]:
        return await self._run_fault(
            operation="d061_fault_stale_output_source",
            coordinator=getattr(self.app, "rd_managed_live_adoption", None),
            mutate=lambda live: self._stale_single(
                live, "switch", expected_source_key="output_state_code_v2"
            ),
            expected_reason_fragment="switch stale",
            authority_name="D061 adopted Manual",
        )

    async def d061_stale_vout(self) -> Dict[str, Any]:
        return await self._run_fault(
            operation="d061_fault_stale_vout_source",
            coordinator=getattr(self.app, "rd_managed_live_adoption", None),
            mutate=lambda live: self._stale_single(live, "voltage"),
            expected_reason_fragment="voltage stale",
            authority_name="D061 adopted Manual",
        )

    async def d061_missing_meta(self) -> Dict[str, Any]:
        return await self._run_fault(
            operation="d061_fault_missing_runtime_meta",
            coordinator=getattr(self.app, "rd_managed_live_adoption", None),
            mutate=self._missing_meta,
            expected_reason_fragment="freshness metadata is missing",
            authority_name="D061 adopted Manual",
        )

    async def d062_stale_regulation(self) -> Dict[str, Any]:
        return await self._run_fault(
            operation="d062_fault_stale_regulation_source",
            coordinator=getattr(self.app, "rd_managed_mix_adoption", None),
            mutate=self._stale_regulation,
            expected_reason_fragment="regulation_code stale",
            authority_name="D062 MIX_ADOPTED",
        )

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict):
            return await self._original_dispatch(request)
        operation = request.get("op")
        if operation not in (_SOURCE_FAULT_OPS | _PROGRAMMED_READBACK_OPS):
            return await self._original_dispatch(request)

        try:
            async with self.control._operation_lock:
                self.control._require_fields(request, {"op"})
                if operation == "d061_fault_stale_temp_source":
                    result = await self.d061_stale_temp()
                elif operation == "d061_fault_stale_output_source":
                    result = await self.d061_stale_output()
                elif operation == "d061_fault_stale_vout_source":
                    result = await self.d061_stale_vout()
                elif operation == "d061_fault_missing_runtime_meta":
                    result = await self.d061_missing_meta()
                elif operation == "d062_fault_stale_regulation_source":
                    result = await self.d062_stale_regulation()
                else:
                    result = await self.b16_hold_stale_set_voltage_readback()
            return {"ok": True, "operation": operation, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self.control._error(str(exc))
        except Exception as exc:
            return self.control._error(
                f"operation rejected: {type(exc).__name__}: {exc}"
            )


def install_physical_test_control_source_faults(
    app: Any,
    control: PhysicalTestControl,
) -> PhysicalTestControlSourceFaults:
    """Compose source-fault operations without creating another listener."""

    existing = getattr(app, "physical_test_control_source_faults", None)
    if isinstance(existing, PhysicalTestControlSourceFaults):
        return existing
    extension = PhysicalTestControlSourceFaults(app, control)
    control.dispatch = extension.dispatch
    app.physical_test_control_source_faults = extension
    return extension
