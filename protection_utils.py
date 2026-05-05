from __future__ import annotations

from typing import Optional


def should_delay_current_ramp(
    target_i: float,
    current_set_i: float,
    target_ocp_raw: Optional[float],
    has_ocp: bool,
) -> bool:
    """Decide whether a short settle delay is needed before raising current."""
    return bool(has_ocp and target_ocp_raw is not None and target_i > current_set_i)


def should_use_startup_settle(
    target_i: float,
    current_set_i: float,
    target_ocp_raw: Optional[float],
    has_ocp: bool,
    turn_on_requested: bool,
) -> bool:
    """Decide whether startup should use a wide OCP and restore it after switch-on."""
    return bool(has_ocp and target_ocp_raw is not None and turn_on_requested and target_i > current_set_i)
