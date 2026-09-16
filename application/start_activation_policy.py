"""Explicit, fail-closed activation policy for the future START ACTIVE mode."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StartExecutionMode(str, Enum):
    SHADOW = "SHADOW"
    DRY_RUN = "DRY_RUN"
    ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class StartActivationDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class StartActivationPolicy:
    execution_mode: StartExecutionMode = StartExecutionMode.SHADOW
    explicit_active_enable: bool = False
    bench_validation_passed: bool = False
    rollback_validation_passed: bool = False
    physical_gate_passed: bool = False

    def evaluate(self, requested_mode: StartExecutionMode | str) -> StartActivationDecision:
        try:
            raw_mode = requested_mode.value if isinstance(requested_mode, StartExecutionMode) else str(requested_mode)
            requested = StartExecutionMode(str(raw_mode).upper())
        except ValueError:
            return StartActivationDecision(False, ("unknown_execution_mode",))

        if requested in {StartExecutionMode.SHADOW, StartExecutionMode.DRY_RUN}:
            return StartActivationDecision(True)

        reasons: list[str] = []
        if self.execution_mode is not StartExecutionMode.ACTIVE:
            reasons.append("policy_mode_not_active")
        if not self.explicit_active_enable:
            reasons.append("explicit_active_enable_missing")
        if not self.bench_validation_passed:
            reasons.append("bench_validation_missing")
        if not self.rollback_validation_passed:
            reasons.append("rollback_validation_missing")
        if not self.physical_gate_passed:
            reasons.append("physical_gate_missing")
        return StartActivationDecision(not reasons, tuple(reasons))
