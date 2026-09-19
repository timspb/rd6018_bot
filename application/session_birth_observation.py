"""Read-only session-birth observation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .session_identity import CurrentSessionTimeline, SessionIdentityModel


class BirthStatus(str, Enum):
    CAPTURED = "SESSION_BIRTH_CAPTURED"
    BLOCKED = "BLOCKED"
    NOT_OBSERVED = "NOT_OBSERVED"


@dataclass(frozen=True)
class SessionBirthEvidence:
    status: BirthStatus
    before_timestamp: float | None
    start_timestamp: float | None
    after_timestamp: float | None
    session: SessionIdentityModel | None
    trace_id: str | None
    profile: str | None
    initial_phase: str | None
    source: str
    missing_fields: tuple[str, ...] = ()


class LiveSessionBirthObserver:
    """Compares supplied before/after snapshots and never changes runtime state."""

    def observe(self, *, before: Mapping[str, Any], after: Mapping[str, Any], start_event: Mapping[str, Any] | None = None) -> SessionBirthEvidence:
        before_active = bool(before.get("active") or before.get("state") == "active")
        after_active = bool(after.get("active") or after.get("state") == "active")
        if before_active or not after_active:
            return SessionBirthEvidence(BirthStatus.NOT_OBSERVED, before.get("timestamp"), None, after.get("timestamp"), None, None, after.get("profile"), after.get("phase"), "supplied snapshots", ("idle_to_active_transition",))
        event = start_event or {}
        session_id = str(event.get("session_id") or after.get("session_id") or "")
        trace_id = str(event.get("trace_id") or after.get("trace_id") or "")
        timestamp = event.get("timestamp") or after.get("timestamp")
        missing = tuple(name for name, value in (("session_id", session_id), ("trace_id", trace_id), ("timestamp", timestamp), ("profile", after.get("profile")), ("initial_phase", after.get("phase"))) if not value)
        if missing:
            return SessionBirthEvidence(BirthStatus.BLOCKED, before.get("timestamp"), timestamp, after.get("timestamp"), None, trace_id or None, after.get("profile"), after.get("phase"), "supplied snapshots", missing)
        identity = SessionIdentityModel.create(session_id=session_id, created_at=float(timestamp), source=str(event.get("source", "V2")), profile=str(after["profile"]), initial_phase=str(after["phase"]))
        return SessionBirthEvidence(BirthStatus.CAPTURED, before.get("timestamp"), float(timestamp), after.get("timestamp"), identity, trace_id, identity.profile, identity.initial_phase, str(event.get("source", "V2")))


class SessionBirthTimelineGuard:
    def accept(self, birth: SessionBirthEvidence, timeline: CurrentSessionTimeline) -> bool:
        return birth.status is BirthStatus.CAPTURED and birth.session is not None and birth.session.session_id == timeline.session_id and not timeline.historical_events_included and timeline.graph_reset


__all__ = ["BirthStatus", "SessionBirthEvidence", "LiveSessionBirthObserver", "SessionBirthTimelineGuard"]
