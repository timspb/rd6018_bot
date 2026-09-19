"""Intent-to-request mapping; no acceptance, transport or physical operation."""

from __future__ import annotations

from .contracts import PhysicalExecutionRequest, PhysicalExecutionResult, PhysicalExecutionStatus, PhysicalFailure
from application.execution_intent.models import ExecutionIntent
from application.safety.models import SafetyDecision, SafetyState


class PhysicalExecutionBoundary:
    def request(self, intent: ExecutionIntent, decision: SafetyDecision, *, timestamp: float) -> PhysicalExecutionRequest | PhysicalExecutionResult:
        if decision.state not in {SafetyState.ALLOW, SafetyState.LIMIT}:
            return PhysicalExecutionResult(PhysicalExecutionStatus.REJECTED, False, True, False, False, False, decision.reason, PhysicalFailure.REJECTED)
        return PhysicalExecutionRequest(intent.source_decision_id, intent.source_decision_id, intent.requested_voltage_v, intent.requested_current_a, decision, timestamp)


__all__ = ["PhysicalExecutionBoundary"]
