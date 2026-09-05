from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from battery_diagnostics import DynamicLoopProbe
from rd6018_telemetry import finite_float, telemetry_freshness


def current_readback_evidence(live: dict[str, Any]) -> Optional[float]:
    """Return the authoritative register-9 programmed-current readback.

    Writable HA number entities are command endpoints and may retain stale
    ``last_reported`` metadata after a write.  D064 must validate the
    force-updated V2 register mirror instead.
    """
    if not isinstance(live.get("_meta"), dict):
        return None
    freshness = telemetry_freshness(live, ["set_current_readback_v2"])
    if not freshness.valid:
        return None
    return finite_float(live.get("set_current_readback_v2"))


@dataclass(frozen=True)
class ProbePlan:
    step_current_a: float
    settle_s: float = 15.0
    sample_count: int = 4
    sample_interval_s: float = 5.0
    readback_tolerance_a: float = 0.06
    max_battery_temp_c: float = 35.0

    def __post_init__(self) -> None:
        if self.step_current_a <= 0:
            raise ValueError("step_current_a must be positive")
        if self.settle_s < 0:
            raise ValueError("settle_s must not be negative")
        if self.sample_count < 2:
            raise ValueError("sample_count must be >=2")
        if self.sample_interval_s <= 0:
            raise ValueError("sample_interval_s must be positive")
        if self.readback_tolerance_a <= 0:
            raise ValueError("readback_tolerance_a must be positive")


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    probe: Optional[DynamicLoopProbe] = None
    reason: str = ""
    output_forced_off: bool = False


class ControlledCurrentProbe:
    """Measure a two-wire charge-response using only a safer current reduction.

    This is NOT an internal-resistance tester. It observes the whole two-wire dynamic
    loop. The executor never raises voltage/current or protection limits. The original
    current setting must be restored and read back; otherwise Output is forced OFF.
    """

    def __init__(self, hass: Any) -> None:
        self.hass = hass

    @staticmethod
    def _output_on(value: Any) -> bool:
        return value is True or str(value).strip().lower() == "on"

    @staticmethod
    def _protection_clear(live: dict[str, Any]) -> bool:
        raw = live.get("protection_code")
        if raw is not None:
            code = finite_float(raw)
            return code is not None and int(code) == 0
        ovp = live.get("ovp_triggered")
        ocp = live.get("ocp_triggered")
        return str(ovp).lower() not in {"on", "true", "1"} and str(ocp).lower() not in {
            "on",
            "true",
            "1",
        }

    def _preflight(self, live: dict[str, Any], plan: ProbePlan) -> Tuple[bool, str, Optional[float]]:
        if not self._output_on(live.get("switch")):
            return False, "output_is_not_on", None
        if not self._protection_clear(live):
            return False, "hardware_protection_not_clear", None
        temp = finite_float(live.get("temp_ext"))
        if temp is None or temp >= plan.max_battery_temp_c:
            return False, "battery_temperature_not_suitable", None
        configured_current = current_readback_evidence(live)
        if configured_current is None or configured_current <= 0:
            return False, "configured_current_unavailable", None
        if plan.step_current_a >= configured_current - plan.readback_tolerance_a:
            return False, "probe_must_reduce_current", configured_current
        ocp = finite_float(live.get("ocp"))
        if ocp is None or ocp + plan.readback_tolerance_a < configured_current:
            return False, "ocp_does_not_cover_original_current", configured_current
        return True, "", configured_current

    async def _wait_current_readback(
        self,
        expected: float,
        *,
        tolerance: float,
        retries: int = 8,
        delay_s: float = 0.25,
    ) -> bool:
        for attempt in range(max(1, retries)):
            if attempt:
                await asyncio.sleep(delay_s)
            live = await self.hass.get_all_live()
            actual = current_readback_evidence(live)
            if actual is not None and abs(actual - expected) <= tolerance:
                return True
        return False

    async def _sample_medians(self, plan: ProbePlan) -> Tuple[float, float]:
        voltages: List[float] = []
        currents: List[float] = []
        for index in range(plan.sample_count):
            if index:
                await asyncio.sleep(plan.sample_interval_s)
            live = await self.hass.get_all_live()
            if not self._output_on(live.get("switch")) or not self._protection_clear(live):
                raise RuntimeError("output_or_protection_changed_during_probe")
            temp = finite_float(live.get("temp_ext"))
            voltage = finite_float(live.get("battery_voltage"))
            current = finite_float(live.get("current"))
            if temp is None or temp >= plan.max_battery_temp_c:
                raise RuntimeError("temperature_changed_during_probe")
            if voltage is None or current is None:
                raise RuntimeError("probe_telemetry_invalid")
            voltages.append(voltage)
            currents.append(current)
        return float(statistics.median(voltages)), float(statistics.median(currents))

    async def _restore_or_off(
        self,
        original_current: float,
        plan: ProbePlan,
    ) -> Tuple[bool, bool]:
        """Return (original_current_restored, output_off_confirmed).

        A failed restore is not equivalent to a successful OFF command. Keep those
        facts separate so callers never report `output_forced_off=True` when the
        shutdown itself failed or could not be confirmed.
        """
        try:
            restored = bool(await self.hass.set_current(original_current))
        except Exception:
            restored = False
        if restored:
            try:
                restored = await self._wait_current_readback(
                    original_current,
                    tolerance=plan.readback_tolerance_a,
                )
            except Exception:
                restored = False
        if restored:
            return True, False

        try:
            off_confirmed = bool(await self.hass.turn_off())
        except Exception:
            off_confirmed = False
        return False, off_confirmed

    @staticmethod
    def _restore_failure_reason(base: str, off_confirmed: bool) -> str:
        return base if off_confirmed else f"{base}_output_off_unconfirmed"

    async def run(
        self,
        *,
        battery_id: str,
        stage: str,
        connection_id: str,
        plan: ProbePlan,
        notes: str = "",
    ) -> ProbeResult:
        initial = await self.hass.get_all_live()
        allowed, reason, original_current = self._preflight(initial, plan)
        if not allowed or original_current is None:
            return ProbeResult(False, reason=reason)

        # Baseline is measured immediately before the controlled step, with the same
        # sensor path used after it so static ADC offset largely cancels in ΔV.
        try:
            baseline_v, baseline_i = await self._sample_medians(plan)
        except Exception as exc:
            return ProbeResult(False, reason=f"baseline_failed:{type(exc).__name__}")

        stepped = False
        try:
            if not await self.hass.set_current(plan.step_current_a):
                return ProbeResult(False, reason="step_programming_failed")
            stepped = True
            if not await self._wait_current_readback(
                plan.step_current_a,
                tolerance=plan.readback_tolerance_a,
            ):
                restored, off_confirmed = await self._restore_or_off(original_current, plan)
                return ProbeResult(
                    False,
                    reason=(
                        "step_readback_mismatch"
                        if restored
                        else self._restore_failure_reason(
                            "step_readback_mismatch_restore_unconfirmed",
                            off_confirmed,
                        )
                    ),
                    output_forced_off=off_confirmed,
                )
            if plan.settle_s:
                await asyncio.sleep(plan.settle_s)
            stepped_v, stepped_i = await self._sample_medians(plan)

            restored, off_confirmed = await self._restore_or_off(original_current, plan)
            if not restored:
                return ProbeResult(
                    False,
                    reason=self._restore_failure_reason(
                        "original_current_restore_unconfirmed",
                        off_confirmed,
                    ),
                    output_forced_off=off_confirmed,
                )

            probe = DynamicLoopProbe(
                battery_id=battery_id,
                measured_at=time.time(),
                stage=stage,
                baseline_voltage_v=baseline_v,
                baseline_current_a=baseline_i,
                stepped_voltage_v=stepped_v,
                stepped_current_a=stepped_i,
                connection_id=connection_id,
                notes=notes,
            )
            return ProbeResult(True, probe=probe)
        except BaseException as exc:
            # asyncio.CancelledError is a BaseException. Cancellation after the current
            # step is still an actuator transition and must not strand RD6018 at the
            # diagnostic setpoint. Perform the same restore-or-OFF cleanup before the
            # cancellation escapes to the task owner.
            restored = False
            off_confirmed = False
            if stepped:
                try:
                    restored, off_confirmed = await asyncio.shield(
                        self._restore_or_off(original_current, plan)
                    )
                except BaseException:
                    restored = False
                    off_confirmed = False

            if not isinstance(exc, Exception):
                raise

            if stepped:
                return ProbeResult(
                    False,
                    reason=(
                        f"probe_failed:{type(exc).__name__}"
                        if restored
                        else self._restore_failure_reason(
                            f"probe_failed:{type(exc).__name__}:restore_unconfirmed",
                            off_confirmed,
                        )
                    ),
                    output_forced_off=off_confirmed,
                )
            return ProbeResult(False, reason=f"probe_failed:{type(exc).__name__}")
