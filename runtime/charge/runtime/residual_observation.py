"""Shared observation state updates for terminal residual sessions."""

from __future__ import annotations

from typing import Any

from runtime.charge.sample_state import mark_stage_sample


def record_residual_observation(
    host: Any, *, stage: str, timestamp_s: float, voltage_v: float,
    current_a: float, temperature_c: float, ah: float, history_interval_s: float,
) -> None:
    """Record residual sample mirrors and history with existing IDLE/DONE rules."""
    mark_stage_sample(host, voltage_v, current_a, temperature_c, ah)
    if stage != host.STAGE_IDLE:
        host._analytics_history.append(
            (timestamp_s, voltage_v, current_a, ah, temperature_c)
        )
        if timestamp_s - host._last_v_i_history_time >= float(history_interval_s):
            host.v_history.append((timestamp_s, voltage_v))
            host.i_history.append((timestamp_s, current_a))
            host._last_v_i_history_time = timestamp_s


def update_residual_cv_clock(host: Any, *, is_cv: bool, timestamp_s: float) -> None:
    """Preserve the residual stages' existing CV-clock mirror update."""
    if is_cv:
        if host._cv_since is None:
            host._cv_since = timestamp_s
    else:
        host._cv_since = None


__all__ = ["record_residual_observation", "update_residual_cv_clock"]
