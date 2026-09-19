"""Aggregated V3 shadow evidence, correlation and replay contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .canonical_events import CanonicalChargeEvent, CanonicalTimelineSnapshot, EventType, build_timeline
from .hardware_validation import RealObservation, ShadowComparisonResult
from .observability import DiagnosticEvent, SystemHealthSnapshot


class ParityCategory(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class ExecutionObservation:
    operation: str
    timestamp: float
    session_id: str
    trace_id: str
    verification_status: str
    result: str


@dataclass(frozen=True)
class ShadowEvidenceBundle:
    evidence_id: str
    observation_id: str
    session_id: str
    trace_id: str
    created_at: float
    events: tuple[CanonicalChargeEvent, ...] = ()
    current_phase: str | None = None
    session_state: str = "UNKNOWN"
    telemetry: tuple[RealObservation, ...] = ()
    execution_observations: tuple[ExecutionObservation, ...] = ()
    active_safety_state: str = "UNKNOWN"
    historical_safety_events: tuple[CanonicalChargeEvent, ...] = ()
    containment_observations: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[DiagnosticEvent, ...] = ()
    health: SystemHealthSnapshot | None = None
    divergences: tuple[ShadowComparisonResult, ...] = ()


@dataclass(frozen=True)
class CorrelationIssue:
    code: str
    reference: str
    detail: str


class EvidenceCorrelationEngine:
    def validate(self, bundle: ShadowEvidenceBundle) -> tuple[CorrelationIssue, ...]:
        issues: list[CorrelationIssue] = []
        if not bundle.trace_id or not bundle.session_id:
            issues.append(CorrelationIssue("MISSING_CORRELATION", bundle.evidence_id, "evidence/session trace is required"))
        if bundle.created_at <= 0:
            issues.append(CorrelationIssue("MISSING_TIMESTAMP", bundle.evidence_id, "created_at is required"))
        last_timestamp = 0.0
        for event in bundle.events:
            if not event.trace_id or not event.session_id:
                issues.append(CorrelationIssue("MISSING_CORRELATION", event.event_id, "event trace/session is required"))
            if event.timestamp <= 0:
                issues.append(CorrelationIssue("MISSING_TIMESTAMP", event.event_id, "event timestamp is required"))
            if event.session_id != bundle.session_id:
                issues.append(CorrelationIssue("CONFLICTING_SESSION", event.event_id, "event belongs to another session"))
            if event.timestamp < last_timestamp:
                issues.append(CorrelationIssue("OUT_OF_ORDER", event.event_id, "event timestamp precedes prior event"))
            last_timestamp = max(last_timestamp, event.timestamp)
        for item in bundle.execution_observations:
            if item.session_id != bundle.session_id or item.trace_id != bundle.trace_id:
                issues.append(CorrelationIssue("CONFLICTING_CORRELATION", item.operation, "execution observation is outside bundle context"))
        return tuple(issues)


@dataclass(frozen=True)
class ReplayResult:
    reconstructed_timeline: CanonicalTimelineSnapshot
    decisions: tuple[Mapping[str, Any], ...]
    divergences: tuple[ShadowComparisonResult, ...]
    execution_performed: bool = False


class ShadowReplayEngine:
    """Replays event evidence into a view only; never creates execution requests."""

    def replay(self, bundle: ShadowEvidenceBundle) -> ReplayResult:
        timeline = build_timeline(bundle.events, session_id=bundle.session_id, current_phase=bundle.current_phase, current_state=bundle.session_state)
        decisions: list[Mapping[str, Any]] = []
        for event in timeline.ordered_events:
            if event.event_type is EventType.PHASE_TRANSITION:
                decisions.append({"type": "phase_transition", "from": event.phase_before, "to": event.phase_after, "reason": event.reason, "trace_id": event.trace_id})
            elif event.event_type.value in {"DeltaStarted", "DeltaCompleted", "HoldStarted", "HoldCompleted", "TerminationDetected"}:
                decisions.append({"type": event.event_type.value, "reason": event.reason, "trace_id": event.trace_id})
        return ReplayResult(timeline, tuple(decisions), bundle.divergences, False)


class ShadowRuntimeEvidenceNamespace:
    """In-memory analytical namespace; it cannot restore runtime state."""

    namespace = "shadow_runtime_evidence"

    def __init__(self) -> None:
        self._bundles: list[ShadowEvidenceBundle] = []
        self._replays: list[ReplayResult] = []

    def store(self, bundle: ShadowEvidenceBundle, replay: ReplayResult | None = None) -> None:
        self._bundles.append(bundle)
        if replay is not None:
            self._replays.append(replay)

    def bundles(self) -> tuple[ShadowEvidenceBundle, ...]:
        return tuple(self._bundles)

    def replays(self) -> tuple[ReplayResult, ...]:
        return tuple(self._replays)

    def restore_runtime_state(self, *_: Any) -> None:
        raise RuntimeError("shadow evidence cannot restore runtime state")


@dataclass(frozen=True)
class ShadowHealthSnapshot:
    collector_status: str
    evidence_freshness_s: float | None
    replay_status: str


@dataclass(frozen=True)
class ShadowDashboardStatus:
    observation_active: bool
    evidence_count: int
    last_divergence: str | None
    parity_state: str


__all__ = ["ParityCategory", "ExecutionObservation", "ShadowEvidenceBundle", "CorrelationIssue", "EvidenceCorrelationEngine", "ReplayResult", "ShadowReplayEngine", "ShadowRuntimeEvidenceNamespace", "ShadowHealthSnapshot", "ShadowDashboardStatus"]
