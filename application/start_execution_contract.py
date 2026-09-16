"""Data-only START execution port contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .runtime_start_service import StartExecutionTrace
from .start_plan import ApprovedStartPlan


@dataclass(frozen=True)
class StartExecutionRequest:
    plan: ApprovedStartPlan
    trace_id: str
    ownership_decision: str
    session_decision: str
    safety_decision: str
    telemetry_evidence: Mapping[str, Any] = field(default_factory=dict)
    execution_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.trace_id).strip():
            raise ValueError("trace_id is required")
        if self.plan.ownership_result != "available":
            raise ValueError("execution request requires available ownership")
        if self.plan.safety_result != "allowed":
            raise ValueError("execution request requires allowed safety")
        if self.session_decision != "clear":
            raise ValueError("execution request requires clear session")
        if self.telemetry_evidence.get("output_on") is not False:
            raise ValueError("execution request requires confirmed Output OFF")
        object.__setattr__(self, "telemetry_evidence", MappingProxyType(dict(self.telemetry_evidence)))
        object.__setattr__(self, "execution_metadata", MappingProxyType(dict(self.execution_metadata)))


@dataclass(frozen=True)
class DryRunPortResult:
    accepted: bool
    trace_id: str
    reason: str
    physical_execution: bool = False


class StartExecutionPort(Protocol):
    def submit(self, request: StartExecutionRequest) -> DryRunPortResult:
        """Accept a validated request without owning runtime or physical state."""


class DryRunExecutionPort:
    """Contract-only port; it records acceptance and never executes START."""

    def submit(self, request: StartExecutionRequest) -> DryRunPortResult:
        if not isinstance(request, StartExecutionRequest):
            raise TypeError("request must be StartExecutionRequest")
        return DryRunPortResult(
            accepted=True,
            trace_id=request.trace_id,
            reason="dry_run_request_accepted",
            physical_execution=False,
        )


def request_from_trace(
    plan: ApprovedStartPlan,
    trace: StartExecutionTrace,
    *,
    trace_id: str,
    execution_metadata: Mapping[str, Any] | None = None,
) -> StartExecutionRequest:
    if not trace.allowed:
        raise ValueError("cannot create execution request from denied trace")
    return StartExecutionRequest(
        plan=plan,
        trace_id=trace_id,
        ownership_decision=trace.ownership_decision,
        session_decision=trace.session_decision,
        safety_decision=trace.safety_decision,
        telemetry_evidence=trace.telemetry_evidence,
        execution_metadata=execution_metadata or {},
    )
