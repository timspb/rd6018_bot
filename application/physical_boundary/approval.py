"""Read-only approval gate for the V3-to-physical boundary.

The gate creates no transport operation.  In simulation mode it can validate
an approval but deliberately returns no physical request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from application.execution_intent.models import ExecutionIntent
from application.safety.models import SafetyDecision, SafetyState

from .contracts import PhysicalExecutionRequest


class ExecutionMode(str, Enum):
    SIMULATION = "SIMULATION"
    REAL_EXECUTION = "REAL_EXECUTION"


class ApprovalStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


REQUIRED_EVIDENCE = (
    "current_state",
    "telemetry_freshness",
    "safety_status",
    "program_identity",
    "lifecycle_state",
)


@dataclass(frozen=True)
class ExecutionApproval:
    decision_id: str
    intent_id: str
    safety_decision: SafetyDecision
    evidence: tuple[tuple[str, str], ...]
    approved_by: str
    timestamp: float
    expiry: float

    def __post_init__(self) -> None:
        for name in ("decision_id", "intent_id", "approved_by"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.timestamp < 0 or self.expiry <= self.timestamp:
            raise ValueError("approval expiry must be after approval timestamp")
        evidence = dict(self.evidence)
        if len(evidence) != len(self.evidence):
            raise ValueError("duplicate evidence keys are not allowed")
        missing = [key for key in REQUIRED_EVIDENCE if not str(evidence.get(key, "")).strip()]
        if missing:
            raise ValueError(f"required approval evidence is missing: {', '.join(missing)}")


@dataclass(frozen=True)
class ApprovalGateResult:
    status: ApprovalStatus
    approval: ExecutionApproval | None
    request: PhysicalExecutionRequest | None
    reason: str


class ExecutionApprovalGate:
    """Validate approval without performing physical execution."""

    def evaluate(
        self,
        intent: ExecutionIntent,
        approval: ExecutionApproval | None,
        *,
        now: float,
        mode: ExecutionMode,
    ) -> ApprovalGateResult:
        if approval is None:
            return ApprovalGateResult(ApprovalStatus.REJECTED, None, None, "approval is required")
        if approval.decision_id != intent.source_decision_id or approval.intent_id != intent.source_decision_id:
            return ApprovalGateResult(ApprovalStatus.REJECTED, approval, None, "approval identity does not match intent")
        if approval.safety_decision.state not in {SafetyState.ALLOW, SafetyState.LIMIT}:
            return ApprovalGateResult(ApprovalStatus.REJECTED, approval, None, "safety decision does not approve execution")
        if now >= approval.expiry:
            return ApprovalGateResult(ApprovalStatus.EXPIRED, approval, None, "approval has expired")
        if mode is ExecutionMode.SIMULATION:
            return ApprovalGateResult(ApprovalStatus.APPROVED, approval, None, "simulation approval validated; physical request suppressed")
        request = PhysicalExecutionRequest(
            intent_id=intent.source_decision_id,
            source_decision=intent.source_decision_id,
            requested_voltage_v=intent.requested_voltage_v,
            requested_current_a=intent.requested_current_a,
            safety_approval=approval.safety_decision,
            timestamp=now,
        )
        return ApprovalGateResult(ApprovalStatus.APPROVED, approval, request, "approval validated")


__all__ = [
    "ApprovalGateResult",
    "ApprovalStatus",
    "ExecutionApproval",
    "ExecutionApprovalGate",
    "ExecutionMode",
    "REQUIRED_EVIDENCE",
]
