"""Observer-only live charge-cycle evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from application.shadow_evidence_chain import EvidenceChainResult, ShadowEvidenceChainValidator
from v3_core.canonical_events import CanonicalChargeEvent, EventType
from v3_core.shadow_runtime_evidence import ReplayResult, ShadowEvidenceBundle, ShadowReplayEngine


class SourceCorrelation(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class LiveCycleState:
    session_id: str | None
    profile: str | None
    phase: str | None
    started_at: float | None
    source: str


@dataclass(frozen=True)
class SourceCorrelationResult:
    field: str
    values: Mapping[str, Any]
    classification: SourceCorrelation
    reason: str


@dataclass(frozen=True)
class CompleteChargeCycleEvidence:
    timeline: tuple[CanonicalChargeEvent, ...]
    telemetry: tuple[Mapping[str, Any], ...]
    readback: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[Mapping[str, Any], ...]
    trace_chain: tuple[str, ...]
    replay_result: ReplayResult | None
    chain_result: EvidenceChainResult


class LiveChargeCycleObserver:
    """Consumes supplied observations only; it has no source clients or writers."""

    def __init__(self, chain_validator: ShadowEvidenceChainValidator | None = None) -> None:
        self._chain_validator = chain_validator or ShadowEvidenceChainValidator()

    def detect(self, *, session: Mapping[str, Any], rd: Mapping[str, Any], esphome: Mapping[str, Any], ha: Mapping[str, Any]) -> LiveCycleState:
        return LiveCycleState(
            session_id=session.get("session_id") or session.get("id"),
            profile=session.get("profile") or session.get("battery"),
            phase=session.get("phase") or session.get("stage") or rd.get("phase"),
            started_at=session.get("started_at"),
            source="session+RD+ESPHome+HA",
        )

    def correlate(self, observations: Mapping[str, Mapping[str, Any]], *, numeric_tolerance: float = 0.05) -> tuple[SourceCorrelationResult, ...]:
        fields = sorted({field for source in observations.values() for field in source})
        results: list[SourceCorrelationResult] = []
        for field in fields:
            values = {source: data[field] for source, data in observations.items() if field in data}
            if len(values) < 2:
                results.append(SourceCorrelationResult(field, values, SourceCorrelation.EXPECTED_DIFFERENCE, "field is unavailable from one or more sources"))
                continue
            numeric = []
            for value in values.values():
                try:
                    numeric.append(float(value))
                except (TypeError, ValueError):
                    numeric = []
                    break
            match = max(numeric) - min(numeric) <= numeric_tolerance if numeric else len({str(value) for value in values.values()}) == 1
            results.append(SourceCorrelationResult(field, values, SourceCorrelation.MATCH if match else SourceCorrelation.CONFLICT, "values agree" if match else "source values differ beyond tolerance"))
        return tuple(results)

    def capture(self, *, events: Iterable[CanonicalChargeEvent], session_id: str, evidence_id: str, observation_id: str, created_at: float, telemetry: Iterable[Mapping[str, Any]] = (), readback: Iterable[Mapping[str, Any]] = (), diagnostics: Iterable[Mapping[str, Any]] = ()) -> CompleteChargeCycleEvidence:
        timeline = tuple(events)
        chain_result = self._chain_validator.validate(timeline, session_id=session_id)
        replay = None
        if timeline:
            bundle = ShadowEvidenceBundle(evidence_id, observation_id, session_id, timeline[0].trace_id, created_at, events=timeline, current_phase=timeline[-1].phase_after, session_state="observed")
            replay = ShadowReplayEngine().replay(bundle)
        return CompleteChargeCycleEvidence(timeline, tuple(telemetry), tuple(readback), tuple(diagnostics), tuple(event.trace_id for event in timeline), replay, chain_result)


__all__ = ["SourceCorrelation", "LiveCycleState", "SourceCorrelationResult", "CompleteChargeCycleEvidence", "LiveChargeCycleObserver"]
