"""Deterministic mapping from a domain decision to a data-only intent."""

from __future__ import annotations

from typing import Any

from .models import ExecutionIntent, IntentValidationResult, SafetyContext, SafetyOutcome
from .policy import SafetyPolicy


class DecisionIntentMapper:
    @staticmethod
    def from_decision(
        decision: Any,
        safety_context: SafetyContext,
        safety_policy: SafetyPolicy,
    ) -> IntentValidationResult:
        if decision.desired_voltage_v is None or decision.desired_current_a is None:
            return IntentValidationResult(SafetyOutcome.DENIED, None, "decision has no executable setpoints")
        decision_id = decision.decision_id or f"{decision.program_id}:{decision.current_phase}:{decision.reason}"
        intent = ExecutionIntent(
            requested_voltage_v=float(decision.desired_voltage_v),
            requested_current_a=float(decision.desired_current_a),
            requested_mode="SETPOINT",
            source_decision_id=decision_id,
            safety_context=safety_context,
            # A decision is the canonical identity for this pure mapping.  Do
            # not mint a different random intent on every deterministic replay.
            intent_id=decision_id,
        )
        return safety_policy.validate(intent)
