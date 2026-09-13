"""Non-actuating protection-reset intents emitted after MIX."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResetProtectionIntent:
    """Data-only request for the outer layer to restore safe idle limits."""

    target_ovp: float
    target_ocp: float
    reason: str
    source_phase: str = "MIX"

    def __post_init__(self) -> None:
        if self.target_ovp <= 0 or self.target_ocp <= 0:
            raise ValueError("reset protection targets must be positive")
        if not self.reason.strip():
            raise ValueError("reset protection reason is required")
        if not self.source_phase.strip():
            raise ValueError("reset protection source phase is required")


def post_mix_reset_intent(target_ovp: float, target_ocp: float, *, reason: str) -> ResetProtectionIntent:
    return ResetProtectionIntent(target_ovp, target_ocp, reason, "MIX")


def emergency_stop_reset_intent(target_ovp: float, target_ocp: float, *, reason: str) -> ResetProtectionIntent:
    return ResetProtectionIntent(target_ovp, target_ocp, reason, "MIX_EMERGENCY_STOP")
