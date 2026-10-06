"""Compatibility-shaped runtime helpers backed by canonical V3 strategy owners."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from runtime.charge.strategy.desulfation_variables import desulfation_duration_seconds
from runtime.charge.strategy.exit_variables import (
    MIX_CC_DELTA_V_EXIT_V,
    MIX_CV_DELTA_I_EXIT_A,
    MIX_CV_DELTA_I_RATIO,
)
from runtime.charge.strategy.main_variables import main_fallback_seconds
from runtime.charge.strategy.mix_variables import (
    mix_finish_hold_seconds,
    mix_max_active_hours,
)
from runtime.charge.strategy.safe_wait_variables import safe_wait_max_seconds


def current_targets(host: Any, temp_c: Optional[float] = None) -> Tuple[float, float]:
    if host.current_stage == host.STAGE_MAIN:
        return host._main_target(temp_c)
    if host.current_stage == host.STAGE_DESULFATION:
        return host._desulf_target(temp_c)
    if host.current_stage == host.STAGE_MIX:
        return host._mix_target(temp_c)
    return (14.0, 1.0)


def target_finish_time(host: Any) -> Optional[float]:
    if host.current_stage == host.STAGE_SAFE_WAIT:
        return host._safe_wait_start + safe_wait_max_seconds()
    if host.current_stage == host.STAGE_DESULFATION:
        return host.stage_start_time + desulfation_duration_seconds()
    if host.current_stage == host.STAGE_MIX:
        if host.finish_timer_start is not None:
            return host.finish_timer_start + mix_finish_hold_seconds()
        hours = mix_max_active_hours(host.battery_type)
        if hours is not None:
            return host.stage_start_time + hours * 3600.0
    return None


def stage_max_hours(host: Any) -> Optional[float]:
    if host.current_stage == host.STAGE_DESULFATION:
        return desulfation_duration_seconds() / 3600.0
    if host.current_stage == host.STAGE_MIX:
        if host.finish_timer_start is not None:
            return mix_finish_hold_seconds() / 3600.0
        hours = mix_max_active_hours(host.battery_type)
        return float(hours) if hours is not None else mix_finish_hold_seconds() / 3600.0
    if host.current_stage == host.STAGE_SAFE_WAIT:
        return safe_wait_max_seconds() / 3600.0
    return None


def mix_current_delta_threshold(host: Any) -> float:
    floor = float(MIX_CV_DELTA_I_EXIT_A.default)
    if host.i_min_recorded is None:
        return floor
    return max(
        floor,
        float(host.i_min_recorded) * float(MIX_CV_DELTA_I_RATIO.default),
    )


def exit_cc_condition(host: Any, v_now: float) -> bool:
    if host.v_max_recorded is None:
        return False
    delta_v = (
        host._custom_delta_threshold
        if host.battery_type == host.PROFILE_CUSTOM
        else float(MIX_CC_DELTA_V_EXIT_V.default)
    )
    return float(v_now) <= float(host.v_max_recorded) - float(delta_v)


def exit_cv_condition(host: Any, i_now: float) -> bool:
    if host.i_min_recorded is None:
        return False
    delta_i = (
        host._custom_delta_threshold
        if host.battery_type == host.PROFILE_CUSTOM
        else mix_current_delta_threshold(host)
    )
    return float(i_now) >= float(host.i_min_recorded) + float(delta_i)


def session_rules_summary(host: Any) -> str:
    if host.battery_type == host.PROFILE_CA:
        return "Main 14.7V; 0.3A/3h -> Mix 16.5V; Mix 20h; SafeWait 2h."
    if host.battery_type == host.PROFILE_EFB:
        return "Main 14.8V; 0.3A/3h -> Mix 16.5V; Mix 24h; SafeWait 2h."
    if host.battery_type == host.PROFILE_AGM:
        return "Main 14.4/14.6/14.8/15.0V; 0.2A/2h -> Mix 16.3V; Mix 10h; SafeWait 2h."
    if host.battery_type == host.PROFILE_CUSTOM:
        return (
            f"Custom {host._custom_main_voltage:.1f}V/{host._custom_main_current:.1f}A; "
            f"delta={host._custom_delta_threshold:.3f}; "
            f"limit={host._custom_time_limit_hours:.1f}h."
        )
    return "Rules unavailable."


def main_stage_limit_seconds() -> float:
    return main_fallback_seconds()


__all__ = [
    "current_targets",
    "exit_cc_condition",
    "exit_cv_condition",
    "main_stage_limit_seconds",
    "mix_current_delta_threshold",
    "session_rules_summary",
    "stage_max_hours",
    "target_finish_time",
]
