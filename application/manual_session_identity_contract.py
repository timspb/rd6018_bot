"""Design-only identity boundary for the legacy Manual session path."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


class ManualIdentityOrigin(str, Enum):
    MANUAL_START = "manual_start"
    RESTORED = "restored"
    RESUMED = "resumed"


class RestoreResolution(str, Enum):
    RESTORE_EXISTING = "RESTORE_EXISTING"
    LINKED_NEW = "LINKED_NEW"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ManualSessionIdentityBoundary:
    session_id: str
    trace_id: str
    created_at: float
    source: str
    profile: str | None
    origin: ManualIdentityOrigin
    linked_session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.session_id.strip() or not self.trace_id.strip() or self.created_at <= 0 or not self.source.strip():
            raise ValueError("manual identity requires session_id, trace_id, created_at and source")
        if self.origin is ManualIdentityOrigin.MANUAL_START and self.linked_session_id:
            raise ValueError("new manual start cannot have a linked predecessor")


@dataclass(frozen=True)
class ManualRestoreDecision:
    resolution: RestoreResolution
    identity: ManualSessionIdentityBoundary | None
    persisted_session_id: str | None
    reason: str


@dataclass(frozen=True)
class ManualSessionEvent:
    event_type: str
    timestamp: float
    identity: ManualSessionIdentityBoundary | None
    phase_before: str | None = None
    phase_after: str | None = None
    reason: str | None = None
    telemetry_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ManualSessionIdentityBoundaryContract:
    """Pure contract factory; it does not write persistence or alter Manual FSM."""

    def new_start(self, *, session_id: str, trace_id: str, created_at: float, source: str, profile: str | None) -> ManualSessionIdentityBoundary:
        return ManualSessionIdentityBoundary(session_id, trace_id, created_at, source, profile, ManualIdentityOrigin.MANUAL_START)

    def resumed(self, *, session_id: str, trace_id: str, created_at: float, source: str, profile: str | None, linked_session_id: str) -> ManualSessionIdentityBoundary:
        if not linked_session_id.strip():
            raise ValueError("resume requires linked predecessor")
        return ManualSessionIdentityBoundary(session_id, trace_id, created_at, source, profile, ManualIdentityOrigin.RESUMED, linked_session_id)

    def restore(self, persisted: Mapping[str, Any], *, now: float) -> ManualRestoreDecision:
        session_id = str(persisted.get("session_id") or "").strip()
        trace_id = str(persisted.get("trace_id") or "").strip()
        if session_id and trace_id:
            try:
                created_at = float(persisted.get("created_at") or persisted.get("started_at") or 0)
            except (TypeError, ValueError):
                return ManualRestoreDecision(RestoreResolution.AMBIGUOUS, None, session_id, "persisted identity timestamp is invalid; do not guess")
            if created_at <= 0:
                return ManualRestoreDecision(RestoreResolution.AMBIGUOUS, None, session_id, "persisted identity timestamp is missing; do not guess")
            identity = ManualSessionIdentityBoundary(session_id, trace_id, created_at, "manual_restore", persisted.get("profile") or persisted.get("battery_id"), ManualIdentityOrigin.RESTORED)
            return ManualRestoreDecision(RestoreResolution.RESTORE_EXISTING, identity, session_id, "persisted identity is complete")
        return ManualRestoreDecision(RestoreResolution.AMBIGUOUS, None, session_id or None, "legacy manual state has no complete identity; do not guess")


class ManualSessionEventBridge:
    """Maps explicit Manual events to canonical events without creating fake lifecycle events."""

    _EVENTS = {item.value: item for item in EventType}

    def to_canonical(self, event: ManualSessionEvent, *, event_id: str) -> CanonicalChargeEvent:
        if event.identity is None:
            raise ValueError("canonical bridge requires explicit manual identity")
        try:
            event_type = self._EVENTS[event.event_type]
        except KeyError as exc:
            raise ValueError(f"unsupported manual event: {event.event_type}") from exc
        metadata = dict(event.metadata or {})
        if event.telemetry_ref:
            metadata["telemetry_ref"] = event.telemetry_ref
        return CanonicalChargeEvent(event_id, event.timestamp, event.identity.session_id, event.identity.trace_id, EventSource.MANUAL, event_type, event.phase_before, event.phase_after, event.identity.profile, event.reason, metadata=metadata)


__all__ = ["ManualIdentityOrigin", "RestoreResolution", "ManualSessionIdentityBoundary", "ManualRestoreDecision", "ManualSessionEvent", "ManualSessionIdentityBoundaryContract", "ManualSessionEventBridge"]
