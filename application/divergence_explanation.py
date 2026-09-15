"""Analysis-only explanations for V2/V3 shadow divergences, Phase 9.1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .v2_v3_comparison import ComparisonContext, ComparisonResult, ComparisonStatus


class DivergenceCategory(str, Enum):
    FSM_DIFF = "FSM_DIFF"
    PROFILE_DIFF = "PROFILE_DIFF"
    STRATEGY_DIFF = "STRATEGY_DIFF"
    SAFETY_DIFF = "SAFETY_DIFF"
    CONFIG_DIFF = "CONFIG_DIFF"
    ACTUATOR_INTENT_DIFF = "ACTUATOR_INTENT_DIFF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DivergenceExplanation:
    category: DivergenceCategory
    source: str
    v2_value: Any
    v3_value: Any
    expected: bool
    confidence: float
    reason: str


@dataclass(frozen=True)
class DivergenceAnalysis:
    trace_id: str
    status: ComparisonStatus
    explanations: tuple[DivergenceExplanation, ...]


class DivergenceExplanationEngine:
    """Explain observed comparison fields without executing either side."""

    def explain(self, result: ComparisonResult, context: ComparisonContext) -> DivergenceAnalysis:
        if result.trace_id != context.trace_id:
            return DivergenceAnalysis(
                context.trace_id,
                ComparisonStatus.UNKNOWN,
                (DivergenceExplanation(
                    DivergenceCategory.UNKNOWN,
                    "trace-correlation",
                    result.trace_id,
                    context.trace_id,
                    False,
                    1.0,
                    "comparison and context trace ids differ",
                ),),
            )
        explanations = tuple(self._explain_difference(item.field, item.v2, item.v3, item.classification) for item in result.differences)
        return DivergenceAnalysis(result.trace_id, result.status, explanations)

    def _explain_difference(self, field: str, v2: Any, v3: Any, classification: ComparisonStatus) -> DivergenceExplanation:
        category, source, reason = self._classify(field, v2, v3)
        expected = classification is ComparisonStatus.EXPECTED_DIFFERENCE
        confidence = 0.95 if source != "unclassified" else 0.35
        return DivergenceExplanation(category, source, v2, v3, expected, confidence, reason)

    @staticmethod
    def _classify(field: str, v2: Any, v3: Any) -> tuple[DivergenceCategory, str, str]:
        if field == "fsm_state":
            return DivergenceCategory.FSM_DIFF, "V1/V2 FSM vs V3 ChargeEngine", "state transition outputs differ"
        if field == "profile":
            return DivergenceCategory.PROFILE_DIFF, "profile registry/chemistry mapping", "profile identity differs"
        if field in {"safety_limits", "warnings", "containment_recommendation"}:
            return DivergenceCategory.SAFETY_DIFF, "safety policy/envelope", "safety output differs and requires explicit review"
        if field == "actuator_intent":
            return DivergenceCategory.ACTUATOR_INTENT_DIFF, "V2/V3 execution boundary", "generated actuator intent differs; no execution performed"
        if field == "strategy_decision":
            keys = set(v2 or {}) | set(v3 or {}) if isinstance(v2, Mapping) or isinstance(v3, Mapping) else set()
            if "mix_budget_hours" in keys:
                return DivergenceCategory.STRATEGY_DIFF, "EFB Mix policy", "known EFB 20 h versus 24 h budget conflict"
            if {"cc_delta_v", "vmax", "current_drop", "delta"} & keys:
                return DivergenceCategory.STRATEGY_DIFF, "CC/CV termination policy", "known Vmax/Delta versus current-drop strategy difference"
            if "watchdog_timeout_s" in keys:
                return DivergenceCategory.STRATEGY_DIFF, "watchdog policy", "known 180 s versus 300 s watchdog difference"
            if "readback_timeout_s" in keys:
                return DivergenceCategory.CONFIG_DIFF, "readback configuration", "known readback timeout difference"
            return DivergenceCategory.STRATEGY_DIFF, "strategy policy", "strategy decision differs"
        if field == "target_values":
            return DivergenceCategory.STRATEGY_DIFF, "charge target strategy", "target values differ"
        if field == "phase":
            return DivergenceCategory.FSM_DIFF, "phase lifecycle", "phase outputs differ"
        return DivergenceCategory.UNKNOWN, "unclassified", "no explanation mapping is registered"


__all__ = [
    "DivergenceCategory", "DivergenceExplanation", "DivergenceAnalysis",
    "DivergenceExplanationEngine",
]
