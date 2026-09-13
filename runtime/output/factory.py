"""Convert an allowed safety decision to a data-only output intent."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.safety.engine import SafetyDecision

from .intent import OutputAction, SafeOutputIntent


class OutputIntentFactory:
    def create(self, decision: SafetyDecision) -> SafeOutputIntent:
        if not decision.allowed:
            raise ValueError("only an allowed SafetyDecision can be converted")
        if decision.reset_protection is not None:
            reset = decision.reset_protection
            return SafeOutputIntent(
                OutputAction.RESET_PROTECTION,
                target_ovp=reset.target_ovp,
                target_ocp=reset.target_ocp,
                source=reset.source_phase,
            )
        if decision.intent is None:
            raise ValueError("an allowed SafetyDecision requires an intent")
        intent = decision.intent
        if intent.completed:
            return SafeOutputIntent(OutputAction.DISABLE, source="safety")
        return SafeOutputIntent(
            OutputAction.ENABLE,
            target_voltage=intent.target_voltage,
            target_current=intent.target_current,
            source="safety",
        )
