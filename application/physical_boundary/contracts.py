"""Immutable physical boundary request/result contracts with no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from application.safety.models import SafetyDecision, SafetyState


class PhysicalExecutionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"


class PhysicalFailure(str, Enum):
    NONE = "NONE"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    MISMATCH = "MISMATCH"
    STALE_READBACK = "STALE_READBACK"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PhysicalExecutionRequest:
    intent_id: str
    source_decision: str
    requested_voltage_v: float
    requested_current_a: float
    safety_approval: SafetyDecision
    timestamp: float

    def __post_init__(self) -> None:
        if not self.intent_id.strip() or not self.source_decision.strip():
            raise ValueError("execution request identity is required")
        if self.requested_voltage_v < 0 or self.requested_current_a < 0:
            raise ValueError("execution targets cannot be negative")
        if self.timestamp < 0:
            raise ValueError("execution request timestamp cannot be negative")


@dataclass(frozen=True)
class PhysicalExecutionResult:
    status: PhysicalExecutionStatus
    accepted: bool
    rejected: bool
    applied: bool
    verified: bool
    mismatch: bool
    reason: str
    failure: PhysicalFailure = PhysicalFailure.NONE

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("execution result reason is required")
        if self.verified and not self.applied:
            raise ValueError("verified result must be applied")


__all__ = ["PhysicalExecutionRequest", "PhysicalExecutionResult", "PhysicalExecutionStatus", "PhysicalFailure"]
