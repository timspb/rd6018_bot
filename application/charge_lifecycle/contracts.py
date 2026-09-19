"""Immutable lifecycle persistence contracts with no runtime side effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class RestoreKind(str, Enum):
    START_NEW = "START_NEW"
    RESUME_EXISTING = "RESUME_EXISTING"
    AMBIGUOUS = "AMBIGUOUS"


class LifecycleEventType(str, Enum):
    SESSION = "SESSION"
    PHASE = "PHASE"
    DELTA = "DELTA"
    HOLD = "HOLD"
    TERMINATION = "TERMINATION"


class TelemetryState(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True)
class DeltaState:
    status: str
    started_at: float | None = None
    completed_at: float | None = None
    evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class HoldState:
    status: str
    started_at: float | None = None
    elapsed_seconds: float = 0.0
    evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SafetyState:
    status: str
    reason: str = ""
    verification: str = "UNKNOWN"


@dataclass(frozen=True)
class ChargeLifecycleSnapshot:
    session_id: str
    battery_identity: str
    program_id: str
    current_phase: str
    phase_started_at: float
    phase_evidence: Tuple[str, ...]
    delta_state: DeltaState
    hold_state: HoldState
    safety_state: SafetyState
    telemetry_timestamp: float | None
    trace_id: str

    def __post_init__(self) -> None:
        for name in ("session_id", "battery_identity", "program_id", "current_phase", "trace_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required for lifecycle persistence")
        if self.phase_started_at < 0:
            raise ValueError("phase_started_at cannot be negative")


@dataclass(frozen=True)
class RestoreResult:
    kind: RestoreKind
    snapshot: ChargeLifecycleSnapshot | None
    reason: str


@dataclass(frozen=True)
class LifecycleEvent:
    event_type: LifecycleEventType
    session_id: str
    trace_id: str
    timestamp: float
    phase: str | None = None

    def __post_init__(self) -> None:
        if not self.session_id.strip() or not self.trace_id.strip():
            raise ValueError("lifecycle event identity is required")
        if self.timestamp < 0:
            raise ValueError("event timestamp cannot be negative")


__all__ = [
    "ChargeLifecycleSnapshot", "DeltaState", "HoldState", "LifecycleEvent",
    "LifecycleEventType", "RestoreKind", "RestoreResult", "SafetyState",
    "TelemetryState",
]
