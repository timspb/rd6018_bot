"""Pure scalar normalization for persisted AUTO charge session restores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class RestoreScalarProjection:
    ah_limit: int
    current_retries: int
    agm_stage_idx: int
    start_ah: float
    stage_start_ah: float
    stage_start_voltage: float
    stage_start_current: float
    stage_start_temp: float
    safe_wait_target_v: float
    safe_wait_target_i: float
    safe_wait_start: float | None
    first_stage_hold_since: float | None
    first_stage_hold_current: float | None
    stuck_current_since: float | None
    stuck_current_value: float | None
    total_start_time: float | None
    stage_start_time: float | None
    target_finish_time: float | None
    target_voltage_raw: float
    target_voltage: float
    target_current: float
    measured_average_current: float


@dataclass(frozen=True)
class RestoreStageTimeline:
    """Pure continuation decision for the saved AUTO stage timeline.

    ``stage_start_time=None`` means leave the host clock untouched. Zero is
    never a valid write sentinel; callers that need an actual timestamp get
    a positive ``now`` or a validated saved timestamp.
    """

    stage: str
    stage_start_time: float | None
    update_finish_timer_start: bool
    finish_timer_start: float | None
    clear_restored_targets: bool
    restored_terminal: bool
    remaining_min: int


def project_restore_stage_timeline(
    *, current_stage: str, main_stage: str, mix_stage: str,
    desulfation_stage: str, done_stage: str, now: float,
    target_finish_time: float | None, saved_stage_start: float,
    existing_finish_timer_start: float | None, mix_done_timer: float,
) -> RestoreStageTimeline:
    """Project the legacy restore continuation branch without host or clock IO."""
    stage = current_stage
    stage_start_time = None
    update_finish_timer_start = False
    finish_timer_start = None
    clear_restored_targets = False
    restored_terminal = False
    remaining_min = 0

    if target_finish_time is None:
        stage_start_time = saved_stage_start if 0 < saved_stage_start <= now else now
    else:
        remaining_sec = target_finish_time - now
        if remaining_sec > 0:
            if current_stage == desulfation_stage:
                phase_duration = 2 * 3600
                stage_start_time = now - (phase_duration - remaining_sec)
            elif current_stage == mix_stage and existing_finish_timer_start is not None:
                update_finish_timer_start = True
                finish_timer_start = target_finish_time - mix_done_timer
            else:
                stage_start_time = saved_stage_start if 0 < saved_stage_start <= now else now
            remaining_min = int(remaining_sec / 60)
        else:
            if current_stage == desulfation_stage:
                stage = main_stage
                clear_restored_targets = True
                stage_start_time = now
            elif current_stage == mix_stage:
                stage = done_stage
                clear_restored_targets = True
                stage_start_time = now
                restored_terminal = True

    return RestoreStageTimeline(
        stage=stage,
        stage_start_time=stage_start_time,
        update_finish_timer_start=update_finish_timer_start,
        finish_timer_start=finish_timer_start,
        clear_restored_targets=clear_restored_targets,
        restored_terminal=restored_terminal,
        remaining_min=remaining_min,
    )


def project_restore_scalars(
    data: Mapping[str, Any], *, ah: float, voltage: float, current: float,
    agm_stage_count: int, max_stage_current: float,
    clamp_voltage: Callable[[float], float],
) -> RestoreScalarProjection:
    """Normalize legacy scalar fields without consulting host, clock, or IO."""
    now_fallback = None

    def optional_clock(name: str, *, zero_is_missing: bool, invalid_fallback: str):
        raw = data.get(name)
        if raw is None or (zero_is_missing and raw == 0):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            if invalid_fallback == "none":
                return None
            if invalid_fallback == "now":
                return now_fallback
            raise AssertionError(invalid_fallback)

    target_v_raw = float(data.get("target_voltage", 14.7))
    target_i_raw = float(data.get("target_current", 1.0))
    target_finish = data.get("target_finish_time")
    return RestoreScalarProjection(
        ah_limit=int(data.get("ah_limit", 60)),
        current_retries=int(data.get("current_retries", 0)),
        agm_stage_idx=max(0, min(int(data.get("agm_stage_idx", 0)), agm_stage_count - 1)),
        start_ah=float(data.get("start_ah", 0)),
        stage_start_ah=float(data.get("stage_start_ah", ah)),
        stage_start_voltage=_float_with_fallback(data.get("stage_start_voltage", voltage), voltage),
        stage_start_current=_float_with_fallback(data.get("stage_start_current", current), current),
        stage_start_temp=_float_with_fallback(data.get("stage_start_temp", 0.0), 0.0),
        safe_wait_target_v=float(data.get("safe_wait_target_v", 0)),
        safe_wait_target_i=float(data.get("safe_wait_target_i", 0)),
        safe_wait_start=optional_clock("safe_wait_start", zero_is_missing=True, invalid_fallback="now"),
        first_stage_hold_since=optional_clock("first_stage_hold_since", zero_is_missing=True, invalid_fallback="none"),
        first_stage_hold_current=optional_clock("first_stage_hold_current", zero_is_missing=False, invalid_fallback="none"),
        stuck_current_since=optional_clock("stuck_current_since", zero_is_missing=True, invalid_fallback="none"),
        stuck_current_value=optional_clock("stuck_current_value", zero_is_missing=False, invalid_fallback="none"),
        total_start_time=optional_clock("total_start_time", zero_is_missing=True, invalid_fallback="now"),
        stage_start_time=optional_clock("stage_start_time", zero_is_missing=True, invalid_fallback="now"),
        target_finish_time=None if target_finish is None else float(target_finish),
        target_voltage_raw=target_v_raw,
        target_voltage=clamp_voltage(target_v_raw),
        target_current=min(max_stage_current, max(0.1, target_i_raw)),
        measured_average_current=max(float(current), 0.1),
    )


def _float_with_fallback(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)
