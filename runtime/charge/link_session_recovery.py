"""Pure route and authorization decisions for link-session recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecoveryRoute(str, Enum):
    NONE = "none"
    ACTIVE_LINK = "active_link"
    IDLE_LINK = "idle_link"
    IDLE_OUTPUT_ON = "idle_output_on"


class RecoveryAction(str, Enum):
    SKIP = "skip"
    REENABLE_ACTIVE = "reenable_active"
    ENABLE_RESTORED = "enable_restored"
    SAFE_WAIT_OFF = "safe_wait_off"
    PROGRAM_RETAINED_OUTPUT = "program_retained_output"


@dataclass(frozen=True)
class RecoveryRouteInput:
    was_unavailable: bool
    stage: str
    idle_stage: str
    done_stage: str
    cooling_stage: str | None
    output_on: bool
    current_a: float
    temperature_available: bool


@dataclass(frozen=True)
class RecoveryAuthorizationInput:
    route: RecoveryRoute
    restored: bool
    auto_enable_authorized: bool
    safe_wait: bool
    ovp_triggered: bool
    ocp_triggered: bool
    input_voltage_ok: bool
    cold_start: bool = False


def choose_recovery_route(state: RecoveryRouteInput) -> RecoveryRoute:
    """Select the existing in-memory or persisted link-recovery route."""
    if not state.temperature_available:
        return RecoveryRoute.NONE
    if state.was_unavailable:
        if (
            state.stage not in {state.idle_stage, state.done_stage, state.cooling_stage}
            and not state.output_on
        ):
            return RecoveryRoute.ACTIVE_LINK
        if state.stage == state.idle_stage:
            return RecoveryRoute.IDLE_LINK
    if (
        not state.was_unavailable
        and state.stage == state.idle_stage
        and state.output_on
        and state.current_a > 0.05
    ):
        return RecoveryRoute.IDLE_OUTPUT_ON
    return RecoveryRoute.NONE


def authorize_recovery_action(state: RecoveryAuthorizationInput) -> RecoveryAction:
    """Choose the post-restore action without interpreting telemetry or stage rules."""
    if state.cold_start:
        # Persisted session is not permission to energize after a process restart.
        return RecoveryAction.SKIP
    if state.route is RecoveryRoute.ACTIVE_LINK:
        return (
            RecoveryAction.REENABLE_ACTIVE
            if not state.ovp_triggered and not state.ocp_triggered and state.input_voltage_ok
            else RecoveryAction.SKIP
        )
    if state.route not in {RecoveryRoute.IDLE_LINK, RecoveryRoute.IDLE_OUTPUT_ON}:
        return RecoveryAction.SKIP
    if not state.restored:
        return RecoveryAction.SKIP
    if not state.auto_enable_authorized or state.ovp_triggered or state.ocp_triggered or not state.input_voltage_ok:
        return RecoveryAction.SKIP
    if state.safe_wait:
        return RecoveryAction.SAFE_WAIT_OFF
    if state.route is RecoveryRoute.IDLE_LINK:
        return RecoveryAction.ENABLE_RESTORED
    return RecoveryAction.PROGRAM_RETAINED_OUTPUT


__all__ = [
    "RecoveryAction",
    "RecoveryAuthorizationInput",
    "RecoveryRoute",
    "RecoveryRouteInput",
    "authorize_recovery_action",
    "choose_recovery_route",
]
