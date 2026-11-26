"""One-cycle orchestration for an active Manual session."""

from __future__ import annotations

import logging
import time

from rd6018_telemetry import finite_float, resolve_regulation
from runtime.charge.evidence.manual_delta import ManualDeltaSample
from runtime.charge.strategy.manual_phase_lifecycle import MANUAL_MIX_FINISH_HOLD_SEC
from runtime.safety.thermal_variables import (
    BATTERY_TEMP_CRITICAL_C,
    BATTERY_TEMP_PAUSE_C,
    MANUAL_COOLING_RESUME_C as MANUAL_COOLING_RESUME_THRESHOLD_C,
)


# Preserve the existing Manual API names while sourcing every threshold from
# the single Safety thermal-variable owner.
MANUAL_COOLING_PAUSE_C = float(BATTERY_TEMP_PAUSE_C.default)
MANUAL_COOLING_RESUME_C = float(MANUAL_COOLING_RESUME_THRESHOLD_C.default)
MANUAL_TEMP_CRITICAL_C = float(BATTERY_TEMP_CRITICAL_C.default)

logger = logging.getLogger("rd6018.manual")


async def observe_manual_session_once(session) -> None:
    self = session
    if not self.is_active or self.request is None:
        return
    live = await self.execution_port.read_live()
    temp = finite_float(live.get("temp_ext"))
    if temp is None:
        # V2 runtime safety already fails closed on missing critical telemetry.
        return
    if temp >= MANUAL_TEMP_CRITICAL_C:
        await self.stop("manual_critical_battery_temperature")
        return
    if self.state is type(self.state).COOLING:
        if temp <= MANUAL_COOLING_RESUME_C:
            await self._resume_after_cooling()
        return
    if temp >= MANUAL_COOLING_PAUSE_C:
        await self._enter_cooling()
        return

    voltage = finite_float(live.get("battery_voltage"))
    current = finite_float(live.get("current"))
    if voltage is None or current is None:
        return
    now = time.time()
    reason = self._threshold_reason(voltage, current)
    if reason is None:
        reason = self._main_tail_reason(live)
    if reason == "manual_main_to_mix":
        await self._advance_profile_to_mix()
        return
    if reason is None:
        reason = self._mix_hold_reason(now=now)
    if reason is None:
        delta_sample = ManualDeltaSample(
            mode=resolve_regulation(live).value,
            voltage_v=voltage,
            current_a=current,
        )
        reason = self._delta_reason(delta_sample, now=now)
        if reason == "manual_delta_confirmed":
            self.finish_hold_started_at = now
            self._persist()
            logger.info(
                "MANUAL_EVIDENCE kind=delta event=hold_start mode=mix hold_hours=%.2f timestamp=%.3f",
                self.request.profile.mix.hold_hours if self.request.profile is not None else MANUAL_MIX_FINISH_HOLD_SEC / 3600.0,
                now,
            )
            reason = None
    if reason is not None:
        await self.stop(reason)


__all__ = [
    "MANUAL_COOLING_PAUSE_C",
    "MANUAL_COOLING_RESUME_C",
    "MANUAL_MIX_FINISH_HOLD_SEC",
    "MANUAL_TEMP_CRITICAL_C",
    "observe_manual_session_once",
]
