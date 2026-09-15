"""Immutable execution intent and safety validation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import uuid4


class SafetyOutcome(str, Enum):
    ALLOWED = "ALLOWED"
    LIMITED = "LIMITED"
    DENIED = "DENIED"


@dataclass(frozen=True)
class SafetyContext:
    telemetry_state: str = "UNKNOWN"
    lease_state: str = "UNKNOWN"
    containment_state: str = "NORMAL"
    verification_state: str = "UNKNOWN"
    limits_reference: str = "unspecified"


@dataclass(frozen=True)
class ExecutionIntent:
    requested_voltage_v: float
    requested_current_a: float
    requested_mode: str
    source_decision_id: str
    safety_context: SafetyContext
    intent_id: str = ""

    def __post_init__(self) -> None:
        if float(self.requested_voltage_v) < 0 or float(self.requested_current_a) < 0:
            raise ValueError("execution intent setpoints cannot be negative")
        if not str(self.requested_mode).strip():
            raise ValueError("requested_mode is required")
        if not str(self.source_decision_id).strip():
            raise ValueError("source_decision_id is required")
        # The id is created when the intent object is created, never inferred
        # from a legacy physical operation or fabricated after the fact.
        if not self.intent_id.strip():
            object.__setattr__(self, "intent_id", uuid4().hex)


@dataclass(frozen=True)
class IntentValidationResult:
    outcome: SafetyOutcome
    intent: Optional[ExecutionIntent]
    reason: str
