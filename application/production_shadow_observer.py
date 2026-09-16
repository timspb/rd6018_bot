"""Production-shaped V3 shadow observer contracts for Phase 10.0.

The observer consumes mirrored inputs and records analysis artifacts in memory.
It has no execution dependency and never mutates V2 or V3 runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .diagnostics_domain import DiagnosticCategory, DiagnosticEvent, DiagnosticSeverity, DiagnosticsDomain
from .divergence_explanation import DivergenceAnalysis, DivergenceExplanationEngine
from .v2_v3_comparison import ComparisonContext, ComparisonResult, DecisionSnapshot, V2V3ComparisonEngine


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ShadowObservationRecord:
    trace_id: str
    input_snapshot: Any
    v2_decision: DecisionSnapshot
    v3_decision: DecisionSnapshot | None
    comparison: ComparisonResult
    explanation: DivergenceAnalysis
    diagnostic: DiagnosticEvent

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id is required")
        object.__setattr__(self, "input_snapshot", _freeze(self.input_snapshot))


V3DecisionProvider = Callable[[ComparisonContext], DecisionSnapshot | None]


class ShadowObservationSession:
    """In-memory observer session; it is not a runtime or persistence owner."""

    def __init__(
        self,
        v3_provider: V3DecisionProvider,
        *,
        comparison_engine: V2V3ComparisonEngine | None = None,
        explanation_engine: DivergenceExplanationEngine | None = None,
        diagnostics: DiagnosticsDomain | None = None,
    ) -> None:
        self._v3_provider = v3_provider
        self._comparison_template = comparison_engine
        self._explanation_engine = explanation_engine or DivergenceExplanationEngine()
        self._diagnostics = diagnostics or DiagnosticsDomain()
        self._records: list[ShadowObservationRecord] = []

    @property
    def records(self) -> tuple[ShadowObservationRecord, ...]:
        return tuple(self._records)

    def observe(self, context: ComparisonContext, v2_decision: DecisionSnapshot) -> ShadowObservationRecord:
        if not isinstance(context, ComparisonContext):
            raise TypeError("ComparisonContext is required")
        if not isinstance(v2_decision, DecisionSnapshot):
            raise TypeError("V2 DecisionSnapshot is required")
        engine = self._comparison_template or V2V3ComparisonEngine(
            lambda _context: v2_decision,
            self._v3_provider,
        )
        comparison = engine.compare(context)
        v3_decision = comparison.v3
        explanation = self._explanation_engine.explain(comparison, context)
        diagnostic = self._diagnostics.event(
            category=DiagnosticCategory.DOMAIN,
            event_type="shadow_observation_recorded",
            severity=DiagnosticSeverity.INFO,
            correlation=self._correlation(context.trace_id),
            source="v3-shadow-observer",
            payload={"comparison_status": comparison.status.value, "explanation_count": len(explanation.explanations)},
        )
        record = ShadowObservationRecord(
            trace_id=context.trace_id,
            input_snapshot=context.telemetry,
            v2_decision=v2_decision,
            v3_decision=v3_decision,
            comparison=comparison,
            explanation=explanation,
            diagnostic=diagnostic,
        )
        self._records.append(record)
        return record

    @staticmethod
    def _correlation(trace_id: str):
        from .diagnostics_domain import TraceCorrelation
        return TraceCorrelation(trace_id, "shadow-observer")


__all__ = ["ShadowObservationRecord", "ShadowObservationSession"]
