"""Application adapter for existing Manual MAIN and MIX evidence decisions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation
from runtime.charge.evidence.first_stage_variables import NEAR_TARGET_MARGIN_V
from runtime.charge.programs.manual import manual_main_tail_reached
from runtime.charge.strategy.manual_phase_lifecycle import (
    MANUAL_MIX_FINISH_HOLD_SEC,
    manual_mix_finish_hold_complete,
)


logger = logging.getLogger("rd6018.manual")


def evaluate_manual_main_tail(session, live: dict[str, Any]) -> Optional[str]:
    self = session
    assert self.request is not None
    if self.request.operation_mode != "main":
        return None
    voltage = finite_float(live.get("battery_voltage"))
    current = finite_float(live.get("current"))
    if voltage is None or current is None:
        return None
    if resolve_regulation(live) is not RegulationMode.CV:
        return None
    if voltage < float(self.request.voltage_v) - float(NEAR_TARGET_MARGIN_V.default):
        return None
    if self.request.profile is not None:
        decision = self.phase_lifecycle.evaluate_main(
            profile=self.request.profile,
            voltage_v=voltage,
            current_a=current,
            is_cv=True,
        )
        self.main_min_confirmations = self.phase_lifecycle.confirmations
        self.main_min_hold_started_at = self.phase_lifecycle.hold_started_at
        if decision is not None:
            return "manual_main_to_mix"
    elif manual_main_tail_reached(
        imin=self._imin,
        current_a=current,
        threshold_a=self.main_tail_current_threshold_a,
    ):
        return "manual_main_cv_imin"
    return None


def evaluate_manual_mix_hold(session, *, now: float) -> Optional[str]:
    self = session
    if self.request is None or self.request.operation_mode != "mix":
        return None
    hold_hours = (
        self.request.profile.mix.hold_hours
        if self.request.profile is not None
        else MANUAL_MIX_FINISH_HOLD_SEC / 3600.0
    )
    if manual_mix_finish_hold_complete(
        operation_mode=self.request.operation_mode,
        hold_started_at=self.finish_hold_started_at,
        configured_hold_hours=(
            self.request.profile.mix.hold_hours
            if self.request.profile is not None
            else None
        ),
        now=now,
    ):
        logger.info(
            "MANUAL_EVIDENCE kind=delta event=hold_complete mode=mix hold_hours=%.2f timestamp=%.3f",
            hold_hours,
            now,
        )
        return "manual_mix_delta_hold_complete"
    return None


__all__ = ["evaluate_manual_main_tail", "evaluate_manual_mix_hold"]
