"""Deterministic D062 fresh-Delta + finish-hold physical validation hook.

This module extends the existing opt-in root-only AF_UNIX physical-test control
plane with one parameterless operation. It never turns Output ON and never writes
V/I/OVP/OCP/protection. The operation requires an already ACTIVE MIX_ADOPTED
session, injects only in-memory post-adoption Delta evidence, then advances only
the coordinator's in-process monotonic test clock by the production 2h hold.

The production observe/terminal path remains authoritative: the first observe must
start the normal sticky finish hold, and the second observe must reach
DELTA_HOLD_COMPLETE and the normal verified-OFF/lease-disarm boundary. This is a
deterministic transition proof, not a two-hour wall-clock endurance claim.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, Dict

from physical_test_control import (
    PhysicalTestControl,
    PhysicalTestControlError,
    _json_value,
)
from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation
from rd_live_adoption import MIX_FINISH_HOLD_S
from rd_managed_mix import ManagedMixState
from signal_analyzer import SignalAnalyzer, SignalEvent, SignalSample


_OPERATION = "d062_test_delta_hold_complete"
_SOURCE_WAIT_S = 30.0
_SOURCE_POLL_S = 0.5
_HOLD_ADVANCE_MARGIN_S = 1.0


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


class PhysicalTestControlD062Delta:
    """One-shot final D062 normal-terminal physical-test extension."""

    def __init__(self, app: Any, control: PhysicalTestControl) -> None:
        self.app = app
        self.control = control
        self._original_dispatch = control.dispatch

    @staticmethod
    def _synthetic_delta_analysis(
        coordinator: Any,
        live: Dict[str, Any],
    ) -> tuple[Any, Dict[str, Any]]:
        """Build mode-correct fresh Delta evidence without touching HA/RD state."""

        authority = getattr(coordinator, "current_authority", None)
        if authority is None:
            raise PhysicalTestControlError("D062 Delta test requires current authority")

        voltage = finite_float(live.get("battery_voltage"))
        if voltage is None:
            voltage = finite_float(live.get("voltage"))
        current = finite_float(live.get("current"))
        temp = finite_float(live.get("temp_ext_v2"))
        if temp is None:
            temp = finite_float(live.get("temp_ext"))
        regulation = resolve_regulation(live)
        if voltage is None or current is None or temp is None:
            raise PhysicalTestControlError("D062 Delta test requires coherent physical U/I/T telemetry")
        if regulation not in {RegulationMode.CV, RegulationMode.CC}:
            raise PhysicalTestControlError("D062 Delta test requires authoritative CV/CC regulation")

        analyzer = SignalAnalyzer()
        analyzer.reset_stage(
            "MIX_ADOPTED",
            target_voltage_v=float(authority.set_voltage_v),
        )
        barrier = max(
            float(getattr(coordinator, "last_source_timestamp_s", 0.0) or 0.0),
            float(getattr(coordinator, "started_at_s", 0.0) or 0.0),
            1.0,
        )
        base = barrier + 1.0
        samples: list[SignalSample] = []

        if regulation is RegulationMode.CV:
            ceiling = float(authority.set_current_a)
            if not math.isfinite(ceiling) or ceiling < 0.08:
                raise PhysicalTestControlError(
                    "D062 CV Delta test requires at least 0.08A current authority"
                )
            imin = min(0.10, ceiling - 0.04)
            imin = max(0.01, imin)
            threshold = max(0.03, imin * 0.30)
            reversed_i = imin + threshold + 0.01
            if reversed_i > ceiling + 1e-9:
                imin = max(0.01, ceiling - 0.05)
                threshold = max(0.03, imin * 0.30)
                reversed_i = imin + threshold + 0.01
            if reversed_i > ceiling + 1e-9:
                raise PhysicalTestControlError(
                    "D062 CV Delta test cannot construct reversal inside current authority"
                )
            target_v = float(authority.set_voltage_v)
            samples = [
                SignalSample(base, target_v, imin, float(temp), is_cv=True),
                SignalSample(base + 120.0, target_v, reversed_i, float(temp), is_cv=True),
                SignalSample(base + 170.0, target_v, reversed_i, float(temp), is_cv=True),
                SignalSample(base + 220.0, target_v, reversed_i, float(temp), is_cv=True),
            ]
            details: Dict[str, Any] = {
                "mode": "CV",
                "imin_a": imin,
                "reversal_current_a": reversed_i,
                "delta_current_a": reversed_i - imin,
                "target_voltage_v": target_v,
            }
        else:
            set_v = float(authority.set_voltage_v)
            vmax = min(set_v - 0.05, float(voltage) + 0.05)
            if not math.isfinite(vmax) or vmax <= 0.10:
                raise PhysicalTestControlError("D062 CC Delta test cannot construct a safe Vmax")
            reversed_v = vmax - 0.05
            if reversed_v <= 0:
                raise PhysicalTestControlError("D062 CC Delta test cannot construct voltage reversal")
            synthetic_i = min(float(authority.set_current_a), max(0.01, float(current)))
            samples = [
                SignalSample(base, vmax, synthetic_i, float(temp), is_cc=True),
                SignalSample(base + 120.0, reversed_v, synthetic_i, float(temp), is_cc=True),
                SignalSample(base + 170.0, reversed_v, synthetic_i, float(temp), is_cc=True),
                SignalSample(base + 220.0, reversed_v, synthetic_i, float(temp), is_cc=True),
            ]
            details = {
                "mode": "CC",
                "vmax_v": vmax,
                "reversal_voltage_v": reversed_v,
                "delta_voltage_v": vmax - reversed_v,
                "current_a": synthetic_i,
            }

        analysis = None
        for sample in samples:
            analysis = analyzer.observe(sample)
        if analysis is None or SignalEvent.END_OF_CHARGE_LIKELY not in analysis.events:
            raise PhysicalTestControlError(
                "D062 synthetic post-adoption Delta did not reach END_OF_CHARGE_LIKELY"
            )
        details["sample_count"] = len(samples)
        details["synthetic_only"] = True
        return analysis, details

    async def _wait_for_new_source(self, coordinator: Any, after_s: float) -> float:
        deadline = asyncio.get_running_loop().time() + _SOURCE_WAIT_S
        while True:
            live = await self.control._raw_live()
            source = coordinator._source_timestamp(live)
            if source is not None and float(source) > float(after_s):
                return float(source)
            if asyncio.get_running_loop().time() >= deadline:
                raise PhysicalTestControlError(
                    "D062 Delta test timed out waiting for a fresh physical source report"
                )
            await asyncio.sleep(_SOURCE_POLL_S)

    @staticmethod
    async def _cancel_background_observer(coordinator: Any) -> None:
        task = getattr(coordinator, "_task", None)
        coordinator._task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def delta_hold_complete(self) -> Dict[str, Any]:
        coordinator = getattr(self.app, "rd_managed_mix_adoption", None)
        if coordinator is None or not bool(getattr(coordinator, "active", False)):
            raise PhysicalTestControlError(
                "d062_test_delta_hold_complete requires ACTIVE MIX_ADOPTED authority"
            )
        manager = getattr(self.app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "pb_managed", False)):
            raise PhysicalTestControlError(
                "d062_test_delta_hold_complete requires in-process PB_MANAGED"
            )

        live_before = await self.control._raw_live()
        if not self.control._is_on(live_before):
            raise PhysicalTestControlError(
                "d062_test_delta_hold_complete requires positively confirmed Output ON"
            )

        analysis, delta_details = self._synthetic_delta_analysis(coordinator, live_before)
        edge = getattr(coordinator, "edge", None)
        lease = getattr(edge, "lease", None)
        if lease is None or not callable(getattr(lease, "read_state", None)):
            raise PhysicalTestControlError("D062 Delta test requires readable edge lease state")
        lease_before = await lease.read_state()
        if not bool(getattr(lease_before, "armed", False)):
            raise PhysicalTestControlError("D062 Delta test requires an armed managed edge lease")

        original_observe = coordinator.analyzer.observe
        original_monotonic = coordinator._monotonic
        observer_cancelled = False
        try:
            await self._cancel_background_observer(coordinator)
            observer_cancelled = True
            if not bool(getattr(coordinator, "active", False)):
                raise PhysicalTestControlError(
                    "D062 authority stopped while suspending the background observer"
                )

            first_floor = float(getattr(coordinator, "last_source_timestamp_s", 0.0) or 0.0)
            first_source = await self._wait_for_new_source(coordinator, first_floor)

            coordinator.analyzer.observe = lambda _sample: analysis
            try:
                await coordinator.observe_once()
            finally:
                coordinator.analyzer.observe = original_observe

            if not bool(getattr(coordinator, "active", False)):
                raise PhysicalTestControlError(
                    "D062 synthetic Delta unexpectedly terminated authority before hold"
                )
            hold_started_at_s = getattr(coordinator, "finish_hold_started_at_s", None)
            hold_anchor = getattr(coordinator, "_finish_hold_anchor_mono", None)
            if hold_started_at_s is None or hold_anchor is None:
                raise PhysicalTestControlError(
                    "D062 production observer did not start the sticky finish hold"
                )
            if "fresh post-adoption Delta accepted" not in str(
                getattr(coordinator, "last_status", "") or ""
            ):
                raise PhysicalTestControlError(
                    "D062 production observer did not report fresh post-adoption Delta acceptance"
                )

            second_floor = float(
                getattr(coordinator, "last_source_timestamp_s", first_source) or first_source
            )
            second_source = await self._wait_for_new_source(coordinator, second_floor)

            hold_advance_s = float(MIX_FINISH_HOLD_S) + _HOLD_ADVANCE_MARGIN_S
            coordinator._monotonic = lambda: float(original_monotonic()) + hold_advance_s
            try:
                await coordinator.observe_once()
            finally:
                coordinator._monotonic = original_monotonic

            if getattr(coordinator, "state", None) is not ManagedMixState.COMPLETED:
                raise PhysicalTestControlError(
                    "D062 accelerated finish hold did not reach COMPLETED"
                )
            if str(getattr(coordinator, "terminal_reason", "") or "") != "DELTA_HOLD_COMPLETE":
                raise PhysicalTestControlError(
                    "D062 accelerated finish hold did not terminate as DELTA_HOLD_COMPLETE"
                )

            live_after = await self.control._raw_live()
            lease_after = await lease.read_state()
            if not self.control._is_off(live_after):
                raise PhysicalTestControlError(
                    "D062 DELTA_HOLD_COMPLETE did not confirm physical Output OFF"
                )
            if bool(getattr(lease_after, "armed", False)):
                raise PhysicalTestControlError(
                    "D062 DELTA_HOLD_COMPLETE left the managed edge lease armed"
                )

            return {
                "completed": True,
                "terminal_reason": str(coordinator.terminal_reason),
                "state": _enum_value(coordinator.state),
                "delta": delta_details,
                "first_fresh_source_s": first_source,
                "second_fresh_source_s": second_source,
                "finish_hold_started_at_s": hold_started_at_s,
                "accelerated_hold_s": hold_advance_s,
                "wall_clock_endurance_claim": False,
                "generation_before": getattr(lease_before, "generation", None),
                "generation_after": getattr(lease_after, "generation", None),
                "lease_armed": getattr(lease_after, "armed", None),
                "remaining_s": getattr(lease_after, "remaining_s", None),
                "output": live_after.get("switch"),
                "output_state_code_v2": live_after.get("output_state_code_v2"),
                "hardware_writes_injected": 0,
            }
        except Exception as exc:
            coordinator.analyzer.observe = original_observe
            coordinator._monotonic = original_monotonic
            if observer_cancelled and bool(
                getattr(coordinator, "active", False) or getattr(coordinator, "off_pending", False)
            ):
                try:
                    await coordinator.force_verified_off(
                        f"PHYSICAL_TEST_D062_DELTA_HOLD_HARNESS_ERROR:{type(exc).__name__}:{exc}",
                        failed=True,
                    )
                except Exception:
                    pass
            if isinstance(exc, PhysicalTestControlError):
                raise
            raise PhysicalTestControlError(
                f"D062 Delta/hold operation rejected: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            coordinator.analyzer.observe = original_observe
            coordinator._monotonic = original_monotonic

    async def dispatch(self, request: Any) -> Dict[str, Any]:
        if not isinstance(request, dict) or request.get("op") != _OPERATION:
            return await self._original_dispatch(request)
        try:
            async with self.control._operation_lock:
                self.control._require_fields(request, {"op"})
                result = await self.delta_hold_complete()
            return {"ok": True, "operation": _OPERATION, "result": _json_value(result)}
        except (PhysicalTestControlError, ValueError, TypeError) as exc:
            return self.control._error(str(exc))
        except Exception as exc:
            return self.control._error(
                f"operation rejected: {type(exc).__name__}: {exc}"
            )


def install_physical_test_control_d062_delta(
    app: Any,
    control: PhysicalTestControl,
) -> PhysicalTestControlD062Delta:
    """Add the final D062 normal-terminal hook to the existing local socket."""

    existing = getattr(app, "physical_test_control_d062_delta", None)
    if isinstance(existing, PhysicalTestControlD062Delta):
        return existing
    extension = PhysicalTestControlD062Delta(app, control)
    control.dispatch = extension.dispatch
    app.physical_test_control_d062_delta = extension
    return extension
