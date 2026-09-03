"""Deterministic source-freshness faults for the local physical-test control plane.

This extension reuses the existing opt-in root-only AF_UNIX server.  Every operation
mutates exactly one in-memory production decision snapshot, never HA/RD state.  The
normal production runtime must detect the bad evidence and perform verified Output
OFF; all later OFF-confirmation reads use the restored real reader.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from physical_test_control import (
    PhysicalTestControl,
    PhysicalTestControlError,
    _json_value,
)
from rd6018_telemetry import RegulationMode, as_bool, resolve_regulation


_SOURCE_FAULT_OPS = {
    "d061_fault_stale_temp_source",
    "d061_fault_stale_output_source",
    "d061_fault_stale_vout_source",
    "d061_fault_missing_runtime_meta",
    "d062_fault_stale_regulation_source",
}
_STALE_TIMESTAMP = "2000-01-01T00:00:00+00:00"


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
        if operation not in _SOURCE_FAULT_OPS:
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
                else:
                    result = await self.d062_stale_regulation()
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
