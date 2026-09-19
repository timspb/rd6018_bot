"""Data-only orchestration from START authority to a dry-run execution gate.

The orchestrator creates lifecycle and intent contracts only.  It never calls
an executor, transport, HA, ESPHome, RD or Modbus implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.start_authority.contracts import (
    InitialState,
    SessionStarted,
    StartDecision,
    StartDecisionStatus,
    StartIdentity,
    StartRequest,
)


@dataclass(frozen=True)
class GateResult:
    """Result of a non-physical safety or approval gate."""

    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("gate reason is required")


@dataclass(frozen=True)
class StartOrchestrationResult:
    request_id: str
    decision: StartDecision
    identity: StartIdentity | None
    lifecycle_event: SessionStarted | None
    execution_intent: ExecutionIntent | None
    blocked_reason: str | None
    physical_request_created: bool = False

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if self.blocked_reason is None and self.decision.status is not StartDecisionStatus.ALLOW:
            raise ValueError("non-allowed orchestration must explain its block")
        if self.physical_request_created:
            raise ValueError("orchestration cannot create physical requests")


Gate = Callable[[StartRequest, ExecutionIntent], GateResult]


class StartAuthority:
    """Small pure authority used by the orchestration layer.

    It decides lifecycle eligibility only; Output state is verified elsewhere.
    """

    def decide(self, request: StartRequest, *, now: float) -> StartDecision:
        if not request.requested_parameters_ref.strip():
            return StartDecision(StartDecisionStatus.AMBIGUOUS, "requested parameters reference is missing")
        identity = StartIdentity.create(created_at=now)
        event = SessionStarted(
            identity=identity,
            timestamp=now,
            program_id=request.program_id,
            initial_state=InitialState.ARMING,
        )
        return StartDecision(
            StartDecisionStatus.ALLOW,
            "start authority accepted lifecycle creation",
            identity=identity,
            lifecycle_event=event,
        )


class StartOrchestrator:
    """Compose START contracts and stop before physical execution."""

    def __init__(self, *, authority: StartAuthority | None = None, safety_gate: Gate | None = None, approval_gate: Gate | None = None) -> None:
        self._authority = authority or StartAuthority()
        self._safety_gate = safety_gate or self._allow_gate
        self._approval_gate = approval_gate or self._allow_gate

    @staticmethod
    def _allow_gate(_request: StartRequest, _intent: ExecutionIntent) -> GateResult:
        return GateResult(True, "gate accepted dry-run intent")

    def orchestrate(self, request: StartRequest, *, now: float) -> StartOrchestrationResult:
        request_id = uuid4().hex
        decision = self._authority.decide(request, now=now)
        if decision.status is not StartDecisionStatus.ALLOW:
            return StartOrchestrationResult(request_id, decision, None, None, None, decision.reason)

        identity = decision.identity
        event = decision.lifecycle_event
        parameters = request.requested_parameters
        voltage = parameters.get("voltage_v")
        current = parameters.get("current_a")
        if voltage is None or current is None:
            return StartOrchestrationResult(
                request_id, decision, identity, event, None,
                "requested execution targets are missing",
            )

        intent = ExecutionIntent(
            requested_voltage_v=float(voltage),
            requested_current_a=float(current),
            requested_mode=request.mode.value,
            source_decision_id=request_id,
            safety_context=SafetyContext(
                telemetry_state="START_REQUEST",
                lease_state="NOT_REQUESTED",
                containment_state="OBSERVE",
                verification_state="PENDING",
                limits_reference=request.requested_parameters_ref,
            ),
        )
        safety = self._safety_gate(request, intent)
        if not safety.allowed:
            return StartOrchestrationResult(request_id, decision, identity, event, intent, safety.reason)
        approval = self._approval_gate(request, intent)
        if not approval.allowed:
            return StartOrchestrationResult(request_id, decision, identity, event, intent, approval.reason)

        # Deliberately no PhysicalExecutionRequest is created.  This is the
        # explicit dry-run stop point before the physical boundary.
        return StartOrchestrationResult(request_id, decision, identity, event, intent, None)


__all__ = ["GateResult", "StartAuthority", "StartOrchestrationResult", "StartOrchestrator"]
