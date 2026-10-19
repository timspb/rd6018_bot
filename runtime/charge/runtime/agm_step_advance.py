"""Typed AGM MAIN step-advance effect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgmStepAdvanceEffect:
    next_stage_index: int
    stage_count: int
    now_s: float
    ah: float
    temperature_c: float
    reason: str


def build_agm_step_advance_effect(
    *,
    current_stage_index: int,
    stage_count: int,
    now_s: float,
    ah: float,
    temperature_c: float,
    reason: str,
) -> AgmStepAdvanceEffect:
    count = max(1, int(stage_count))
    next_index = min(int(current_stage_index) + 1, count - 1)
    return AgmStepAdvanceEffect(
        next_stage_index=next_index,
        stage_count=count,
        now_s=float(now_s),
        ah=float(ah),
        temperature_c=float(temperature_c),
        reason=str(reason),
    )


def apply_agm_step_advance_effect(
    host: Any,
    effect: AgmStepAdvanceEffect,
    actions: dict[str, Any],
) -> None:
    host._agm_stage_idx = effect.next_stage_index
    host.stage_start_time = effect.now_s
    host._stage_start_ah = effect.ah
    host._reset_delta_and_blanking(effect.now_s)
    host._main_sample_evidence.reset()

    target_v, target_i = host._main_target(effect.temperature_c)
    actions["set_voltage"] = target_v
    actions["set_current"] = target_i
    host._add_phase_limits(actions, target_v, target_i)
    actions["notify"] = (
        f"<b>🚀 V2 AGM ступень {effect.next_stage_index + 1}/{effect.stage_count}:</b> "
        f"{target_v:.2f}В / {target_i:.2f}А — {effect.reason}."
    )
    actions["log_event"] = f"V2_AGM_STEP_{effect.next_stage_index + 1}"


__all__ = [
    "AgmStepAdvanceEffect",
    "apply_agm_step_advance_effect",
    "build_agm_step_advance_effect",
]
