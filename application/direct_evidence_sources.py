"""Read-only direct evidence source contracts and source-to-canonical helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

from v3_core.canonical_events import CanonicalChargeEvent, EventNormalizer, EventSource
from v3_core.shadow_runtime_evidence import ShadowEvidenceBundle


class ReadOnlyESPHomeReader(Protocol):
    def __call__(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ESPHomeEvidenceSnapshot:
    entities: Mapping[str, Any]
    availability: str
    observed_at: float
    device_health: Mapping[str, Any]
    source: str = "ESPHome-direct-read-only"


class ESPHomeEvidenceSource:
    """Adapts caller-supplied ESPHome state; it has no service/write surface."""

    def __init__(self, reader: ReadOnlyESPHomeReader) -> None:
        self._reader = reader

    def collect(self) -> ESPHomeEvidenceSnapshot:
        raw = dict(self._reader())
        if any(key in raw for key in ("services", "commands", "writes")):
            raise ValueError("ESPHome evidence source accepts state only")
        return ESPHomeEvidenceSnapshot(
            entities=dict(raw.get("entities", {})),
            availability=str(raw.get("availability", "unknown")),
            observed_at=float(raw.get("timestamp", 0.0)),
            device_health=dict(raw.get("device_health", {})),
        )


@dataclass(frozen=True)
class TraceCorrelationIssue:
    code: str
    event_id: str
    detail: str


class TraceCorrelationValidator:
    def validate(self, events: Iterable[CanonicalChargeEvent], *, session_id: str, trace_id: str) -> tuple[TraceCorrelationIssue, ...]:
        issues: list[TraceCorrelationIssue] = []
        seen: set[str] = set()
        for event in events:
            if not event.trace_id:
                issues.append(TraceCorrelationIssue("MISSING_TRACE", event.event_id, "trace_id is required"))
            elif event.trace_id != trace_id:
                issues.append(TraceCorrelationIssue("ORPHAN_TRACE", event.event_id, "event is outside bundle trace"))
            if not event.session_id:
                issues.append(TraceCorrelationIssue("MISSING_SESSION", event.event_id, "session_id is required"))
            elif event.session_id != session_id:
                issues.append(TraceCorrelationIssue("CROSS_SESSION", event.event_id, "event is outside bundle session"))
            if event.event_id in seen:
                issues.append(TraceCorrelationIssue("DUPLICATE_EVENT", event.event_id, "event id is duplicated"))
            seen.add(event.event_id)
        return tuple(issues)


@dataclass(frozen=True)
class RuntimeEventSourceRecord:
    event_type: str
    source: str
    owner: str
    timestamp: float | None
    availability: str


def default_runtime_event_inventory() -> tuple[RuntimeEventSourceRecord, ...]:
    return (
        RuntimeEventSourceRecord("START", "manual_session_v2/journal", "V2 production owner", None, "available-partial"),
        RuntimeEventSourceRecord("phase transitions", "systemd journal/manual session", "V2 production owner", None, "available-partial"),
        RuntimeEventSourceRecord("Delta", "runtime diagnostics/history", "V2 production owner", None, "not-proven"),
        RuntimeEventSourceRecord("Hold", "runtime diagnostics/history", "V2 production owner", None, "not-proven"),
        RuntimeEventSourceRecord("termination", "runtime diagnostics/history", "V2 production owner", None, "not-proven"),
        RuntimeEventSourceRecord("STOP", "journal/manual session", "V2 production owner", None, "available-partial"),
    )


class EvidenceChainReassembler:
    """Converts supplied raw event records into a shadow bundle; no source I/O."""

    def __init__(self, normalizer: EventNormalizer | None = None) -> None:
        self._normalizer = normalizer or EventNormalizer()

    def reassemble(self, raw_events: Iterable[Mapping[str, Any]], *, session_id: str, trace_id: str, evidence_id: str, observation_id: str, created_at: float, source: EventSource = EventSource.JOURNAL) -> ShadowEvidenceBundle:
        events = tuple(self._normalizer.normalize(raw, source=source, session_id=session_id, trace_id=trace_id, event_id=f"{evidence_id}-{index}") for index, raw in enumerate(raw_events, 1))
        return ShadowEvidenceBundle(evidence_id, observation_id, session_id, trace_id, created_at, events=events)


__all__ = ["ESPHomeEvidenceSnapshot", "ESPHomeEvidenceSource", "TraceCorrelationIssue", "TraceCorrelationValidator", "RuntimeEventSourceRecord", "default_runtime_event_inventory", "EvidenceChainReassembler"]
