"""Shadow START orchestration with no runtime or physical side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .start_plan import ApprovedStartPlan


@dataclass(frozen=True)
class StartExecutionTrace:
    profile: str
    chemistry: str
    recipe_id: str
    target_voltage_v: float
    target_current_a: float
    ownership_decision: str
    session_decision: str
    safety_decision: str
    controller_handoff_decision: str
    allowed: bool
    reasons: tuple[str, ...] = ()
    telemetry_evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StartTraceComparison:
    status: str
    fields: tuple[str, ...] = ()
    v2: Mapping[str, Any] = field(default_factory=dict)
    v3: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""


class RuntimeStartService:
    """Build a START handoff trace; deliberately does not execute the handoff."""

    def build_trace(self, plan: ApprovedStartPlan) -> StartExecutionTrace:
        evidence = dict(plan.telemetry_evidence)
        reasons: list[str] = []

        ownership = "accepted" if plan.ownership_result == "available" else "denied"
        if ownership == "denied":
            reasons.append("ownership_not_available")

        active_session = evidence.get("active_session")
        session = "clear" if active_session is False else "unknown"
        if active_session is not False:
            reasons.append("session_state_not_confirmed")

        safety = "accepted" if plan.safety_result == "allowed" else "denied"
        if safety == "denied":
            reasons.append("safety_not_allowed")

        if evidence.get("output_on") is not False:
            reasons.append("output_state_not_confirmed_off")

        return StartExecutionTrace(
            profile=plan.profile,
            chemistry=plan.chemistry,
            recipe_id=plan.recipe_id,
            target_voltage_v=plan.target_preview.voltage_v,
            target_current_a=plan.target_preview.current_a,
            ownership_decision=ownership,
            session_decision=session,
            safety_decision=safety,
            controller_handoff_decision="deferred_no_mutation",
            allowed=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            telemetry_evidence=evidence,
        )

    def create_execution_request(
        self,
        plan: ApprovedStartPlan,
        *,
        trace_id: str,
        execution_metadata: Mapping[str, Any] | None = None,
    ):
        """Create a data-only port request; no execution owner is invoked."""
        from .start_execution_contract import request_from_trace

        trace = self.require_approved_trace(plan)
        return request_from_trace(
            plan,
            trace,
            trace_id=trace_id,
            execution_metadata=execution_metadata,
        )

    def require_approved_trace(self, plan: ApprovedStartPlan) -> StartExecutionTrace:
        trace = self.build_trace(plan)
        if not trace.allowed:
            raise ValueError("approved START plan failed shadow handoff: " + ", ".join(trace.reasons))
        return trace


def compare_start_execution_trace(
    v2: Mapping[str, Any],
    trace: StartExecutionTrace,
) -> StartTraceComparison:
    """Compare captured V2 expectations with a non-executing V3 trace."""
    v3 = {
        "profile": trace.profile,
        "chemistry": trace.chemistry,
        "recipe_id": trace.recipe_id,
        "target_voltage_v": trace.target_voltage_v,
        "target_current_a": trace.target_current_a,
        "ownership": trace.ownership_decision,
        "session": trace.session_decision,
        "safety": trace.safety_decision,
        "allowed": trace.allowed,
    }
    fields = tuple(sorted(key for key in set(v2) | set(v3) if v2.get(key) != v3.get(key)))
    return StartTraceComparison("MATCH" if not fields else "MISMATCH", fields, dict(v2), v3)
