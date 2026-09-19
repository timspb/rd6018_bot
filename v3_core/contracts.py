"""Pure V3 contracts and value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class ActuatorOperation(str, Enum):
    OUTPUT_ON = "OUTPUT_ON"
    OUTPUT_OFF = "OUTPUT_OFF"
    SET_VOLTAGE = "SET_VOLTAGE"
    SET_CURRENT = "SET_CURRENT"
    STOP = "STOP"
    CONTAINMENT = "CONTAINMENT"


class SafetyAction(str, Enum):
    ALLOW = "ALLOW"
    OBSERVE = "OBSERVE"
    CONTAIN = "CONTAIN"


@dataclass(frozen=True)
class TelemetrySnapshot:
    voltage: float | None
    current: float | None
    temperature: float | None
    output_on: bool | None
    captured_at: datetime
    source: str
    age_s: float


@dataclass(frozen=True)
class ActuatorIntent:
    operation: ActuatorOperation
    target: Any
    reason: str
    trace_id: str
    owner: str = "V3 Execution Boundary"

    def __post_init__(self) -> None:
        for value in (self.reason, self.trace_id, self.owner):
            if not value.strip():
                raise ValueError("intent identity is required")


@dataclass(frozen=True)
class SafetySignal:
    kind: str
    healthy: bool
    reason: str
    trace_id: str


@dataclass(frozen=True)
class SafetyDecision:
    action: SafetyAction
    reason: str
    trace_id: str
    owner: str = "V3 Safety Domain"


@dataclass(frozen=True)
class DomainDecision:
    state: str
    phase: str
    reason: str
    trace_id: str
    intent: ActuatorIntent | None = None
    safety: SafetyDecision | None = None


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    executed: bool
    operation: ActuatorOperation | None
    reason: str
    trace_id: str


__all__ = [
    "ActuatorOperation", "SafetyAction", "TelemetrySnapshot", "ActuatorIntent",
    "SafetySignal", "SafetyDecision", "DomainDecision", "ExecutionResult",
]
