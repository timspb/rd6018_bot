"""Read-only explanations for current V3 shadow observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .active_session_parity import ActiveSessionParityEvidence, ActiveSessionObservation


@dataclass(frozen=True)
class DecisionExplanation:
    current_state: str | None
    current_phase: str | None
    strategy: str | None
    reason: str | None
    evidence: tuple[str, ...]
    confidence: str
    expected_next_transition: str | None


@dataclass(frozen=True)
class PhaseExplanation:
    phase: str | None
    why_entered: str | None
    why_remains: str | None
    transition_conditions: tuple[str, ...]
    unmet_conditions: tuple[str, ...]


@dataclass(frozen=True)
class SafetyExplanation:
    state: str
    protections: tuple[str, ...]
    stale_data: tuple[str, ...]
    blockers: tuple[str, ...]
    historical_faults: tuple[str, ...]


@dataclass(frozen=True)
class OperatorExplanation:
    decision: DecisionExplanation
    phase: PhaseExplanation
    safety: SafetyExplanation
    comparison: str
    unknown_reasons: tuple[str, ...]


class DecisionExplanationEngine:
    """Explain supplied facts; never infer a missing transition or safety result."""

    def explain(self, *, observation: ActiveSessionObservation, parity: ActiveSessionParityEvidence, evidence: Mapping[str, Any] | None = None) -> OperatorExplanation:
        evidence = evidence or {}
        unknown: list[str] = []
        strategy = evidence.get("strategy")
        reason = evidence.get("reason")
        next_transition = evidence.get("expected_next_transition")
        if strategy is None:
            unknown.append("strategy evidence is missing")
        if reason is None:
            unknown.append("decision reason evidence is missing")
        if next_transition is None:
            unknown.append("next transition is not explicitly evidenced")
        decision = DecisionExplanation(observation.state, observation.phase, strategy, reason, tuple(str(item) for item in evidence.get("evidence", ())), observation.confidence, str(next_transition) if next_transition is not None else None)

        transition_conditions = tuple(str(item) for item in evidence.get("transition_conditions", ()))
        unmet_conditions = tuple(str(item) for item in evidence.get("unmet_conditions", ()))
        phase = PhaseExplanation(observation.phase, evidence.get("why_entered"), evidence.get("why_remains"), transition_conditions, unmet_conditions)

        historical_faults = tuple(str(item) for item in evidence.get("historical_faults", ()))
        safety = SafetyExplanation(str(evidence.get("safety_state", "UNKNOWN")), tuple(str(item) for item in evidence.get("protections", ())), tuple(str(item) for item in evidence.get("stale_data", ())), tuple(str(item) for item in evidence.get("blockers", ())), historical_faults)
        if safety.state == "UNKNOWN":
            unknown.append("safety state is not evidenced")
        return OperatorExplanation(decision, phase, safety, parity.comparison.value, tuple(unknown))


__all__ = ["DecisionExplanation", "PhaseExplanation", "SafetyExplanation", "OperatorExplanation", "DecisionExplanationEngine"]
