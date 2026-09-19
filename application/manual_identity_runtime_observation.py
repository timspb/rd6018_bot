"""Observer-only runtime evidence contracts for Manual identity validation.

This module consumes supplied snapshots/events.  It never starts, stops, restores,
persists, renews a lease, or calls a physical adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from v3_core.canonical_events import CanonicalChargeEvent
from v3_core.shadow_runtime_evidence import ReplayResult

from .manual_session_identity_contract import ManualSessionIdentityBoundaryContract


class ManualIdentityObservationStatus(str, Enum):
    VALIDATED = "MANUAL_IDENTITY_RUNTIME_VALIDATED"
    BLOCKED = "BLOCKED"
    NOT_OBSERVED = "NOT_OBSERVED"


@dataclass(frozen=True)
class ManualSessionEvidenceBundle:
    status: ManualIdentityObservationStatus
    session_id: str | None
    trace_id: str | None
    events: tuple[CanonicalChargeEvent, ...]
    telemetry: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[Mapping[str, Any], ...]
    readback: tuple[Mapping[str, Any], ...]
    replay_result: ReplayResult | None
    ui_timeline_valid: bool
    missing_fields: tuple[str, ...] = ()


class ManualIdentityRuntimeObserver:
    """Validate a supplied Manual transition without creating missing identity."""

    def observe_start(self, *, before: Mapping[str, Any], after: Mapping[str, Any], start_event: Mapping[str, Any] | None = None) -> ManualSessionEvidenceBundle:
        before_active = bool(before.get("active") or before.get("state") == "active")
        after_active = bool(after.get("active") or after.get("state") == "active")
        if before_active or not after_active:
            return self._empty(ManualIdentityObservationStatus.NOT_OBSERVED, ("idle_to_active_transition",))

        event = start_event or {}
        values = {
            "session_id": event.get("session_id") or after.get("session_id"),
            "trace_id": event.get("trace_id") or after.get("trace_id"),
            "timestamp": event.get("timestamp") or after.get("started_at"),
            "profile": event.get("profile") or after.get("profile") or after.get("battery_id"),
            "source": event.get("source") or after.get("source"),
        }
        missing = tuple(name for name, value in values.items() if value in (None, ""))
        if missing:
            return self._empty(ManualIdentityObservationStatus.BLOCKED, missing)
        if before.get("session_id") == values["session_id"]:
            return self._empty(ManualIdentityObservationStatus.BLOCKED, ("new_session_identity",))
        return ManualSessionEvidenceBundle(
            ManualIdentityObservationStatus.VALIDATED,
            str(values["session_id"]),
            str(values["trace_id"]),
            (), (), (), (), None, bool(after.get("graph_reset", True)), (),
        )

    def capture_bundle(self, *, events: Iterable[CanonicalChargeEvent], telemetry: Iterable[Mapping[str, Any]] = (), diagnostics: Iterable[Mapping[str, Any]] = (), readback: Iterable[Mapping[str, Any]] = (), replay_result: ReplayResult | None = None, ui_timeline_valid: bool = True) -> ManualSessionEvidenceBundle:
        captured = tuple(events)
        if not captured:
            return self._empty(ManualIdentityObservationStatus.BLOCKED, ("events",))
        session_ids = {event.session_id for event in captured}
        trace_ids = {event.trace_id for event in captured}
        missing = tuple(name for name, values in (("session_id", session_ids), ("trace_id", trace_ids)) if len(values) != 1 or not next(iter(values), ""))
        if not ui_timeline_valid:
            missing += ("ui_timeline",)
        status = ManualIdentityObservationStatus.VALIDATED if not missing else ManualIdentityObservationStatus.BLOCKED
        return ManualSessionEvidenceBundle(status, next(iter(session_ids), None), next(iter(trace_ids), None), captured, tuple(telemetry), tuple(diagnostics), tuple(readback), replay_result, ui_timeline_valid, missing)

    def classify_legacy_restore(self, persisted: Mapping[str, Any], *, now: float) -> str:
        return ManualSessionIdentityBoundaryContract().restore(persisted, now=now).resolution.value

    @staticmethod
    def _empty(status: ManualIdentityObservationStatus, missing: tuple[str, ...]) -> ManualSessionEvidenceBundle:
        return ManualSessionEvidenceBundle(status, None, None, (), (), (), (), None, False, missing)


__all__ = ["ManualIdentityObservationStatus", "ManualSessionEvidenceBundle", "ManualIdentityRuntimeObserver"]
