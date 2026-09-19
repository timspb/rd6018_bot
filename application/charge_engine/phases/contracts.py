"""Immutable, infrastructure-free phase lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple


class CanonicalPhase(str, Enum):
    PREP = "PREP"
    MAIN = "MAIN"
    DESULFATION = "DESULFATION"
    MIX = "MIX"
    HOLD = "HOLD"
    SAFE_WAIT = "SAFE_WAIT"
    DONE = "DONE"


class TimeoutPolicy(str, Enum):
    NONE = "NONE"
    REPORT = "REPORT"
    INTERRUPT = "INTERRUPT"
    COMPLETE_WITH_WARNING = "COMPLETE_WITH_WARNING"


class InterruptionPolicy(str, Enum):
    NONE = "NONE"
    PAUSE = "PAUSE"
    SAFE_WAIT = "SAFE_WAIT"
    ABORT = "ABORT"


class RecoveryPolicy(str, Enum):
    NONE = "NONE"
    RECHECK_ENTRY = "RECHECK_ENTRY"
    RESUME = "RESUME"
    RESTART_PHASE = "RESTART_PHASE"


class PhaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXIT_READY = "EXIT_READY"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"


@dataclass(frozen=True)
class DeltaPolicy:
    """Program-owned evidence policy; it never performs safety or I/O."""

    start_condition: str
    completion_condition: str
    timeout_seconds: float | None
    measurements: Tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.start_condition.strip() or not self.completion_condition.strip():
            raise ValueError("delta start and completion conditions are required")
        if self.timeout_seconds is not None and self.timeout_seconds < 0:
            raise ValueError("delta timeout cannot be negative")
        if not self.measurements:
            raise ValueError("delta measurements are required")
        if not self.reason.strip():
            raise ValueError("delta reason is required")


@dataclass(frozen=True)
class HoldPolicy:
    """Program-owned hold contract with explicit interruption semantics."""

    start_condition: str
    target_duration_seconds: float | None
    exit_condition: str
    interruption: InterruptionPolicy
    reason: str

    def __post_init__(self) -> None:
        if not self.start_condition.strip() or not self.exit_condition.strip():
            raise ValueError("hold start and exit conditions are required")
        if self.target_duration_seconds is not None and self.target_duration_seconds < 0:
            raise ValueError("hold duration cannot be negative")
        if not self.reason.strip():
            raise ValueError("hold reason is required")


@dataclass(frozen=True)
class PhaseContract:
    phase_id: str
    entry_conditions: Tuple[str, ...]
    exit_conditions: Tuple[str, ...]
    confirmation_requirements: Tuple[str, ...]
    timeout_policy: TimeoutPolicy
    timeout_seconds: float | None
    interruption_policy: InterruptionPolicy
    recovery_policy: RecoveryPolicy
    delta_policy: DeltaPolicy | None = None
    hold_policy: HoldPolicy | None = None

    def __post_init__(self) -> None:
        if not self.phase_id.strip():
            raise ValueError("phase_id is required")
        if not self.entry_conditions or not self.exit_conditions:
            raise ValueError("phase entry and exit conditions are required")
        if self.timeout_seconds is not None and self.timeout_seconds < 0:
            raise ValueError("phase timeout cannot be negative")
        if self.timeout_policy is TimeoutPolicy.NONE and self.timeout_seconds is not None:
            raise ValueError("timeout duration requires a timeout policy")


@dataclass(frozen=True)
class PhaseEvaluation:
    phase_id: str
    status: PhaseStatus
    reason: str
    next_phase: str | None = None
    evidence: Tuple[str, ...] = ()


__all__ = [
    "CanonicalPhase", "DeltaPolicy", "HoldPolicy", "InterruptionPolicy",
    "PhaseContract", "PhaseEvaluation", "PhaseStatus", "RecoveryPolicy",
    "TimeoutPolicy",
]
