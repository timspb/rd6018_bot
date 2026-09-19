"""In-memory live-shadow evidence contracts; no persistence or external I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from .hardware_validation import ShadowComparisonCategory, ShadowComparisonResult


def snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(payload).hexdigest()


@dataclass(frozen=True)
class ShadowEvidenceRecord:
    timestamp: float
    trace_id: str
    session_id: str
    input_snapshot_hash: str
    source: str
    comparison: ShadowComparisonResult
    diagnostics_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionEvidence:
    session_id: str
    started_at: float
    profile: str
    phase_timeline: tuple[Mapping[str, Any], ...] = ()
    telemetry_history: tuple[Mapping[str, Any], ...] = ()
    meaningful_transitions: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ShadowDashboardView:
    health: str
    parity_status: str
    divergences: int
    evidence_count: int


class LiveShadowEvidenceCollector:
    """Accepts supplied observations only; never reads or writes external systems."""

    def __init__(self) -> None:
        self._evidence: list[ShadowEvidenceRecord] = []
        self._sessions: dict[str, SessionEvidence] = {}

    def record(self, *, timestamp: float, trace_id: str, session_id: str, source: str,
               input_snapshot: Mapping[str, Any], comparison: ShadowComparisonResult,
               diagnostics_references: tuple[str, ...] = ()) -> ShadowEvidenceRecord:
        record = ShadowEvidenceRecord(timestamp, trace_id, session_id, snapshot_hash(input_snapshot), source, comparison, diagnostics_references)
        self._evidence.append(record)
        return record

    def register_session(self, session: SessionEvidence) -> None:
        if not session.session_id.strip():
            raise ValueError("session_id is required")
        self._sessions[session.session_id] = session

    def evidence(self) -> tuple[ShadowEvidenceRecord, ...]:
        return tuple(self._evidence)

    def sessions(self) -> tuple[SessionEvidence, ...]:
        return tuple(self._sessions.values())

    def dashboard(self) -> ShadowDashboardView:
        blockers = sum(item.comparison.category is ShadowComparisonCategory.BLOCKER for item in self._evidence)
        warnings = sum(item.comparison.category is ShadowComparisonCategory.WARNING for item in self._evidence)
        status = "BLOCKED" if blockers else ("WARNING" if warnings else "MATCH")
        return ShadowDashboardView("OBSERVING", status, blockers + warnings, len(self._evidence))


__all__ = ["snapshot_hash", "ShadowEvidenceRecord", "SessionEvidence", "ShadowDashboardView", "LiveShadowEvidenceCollector"]
