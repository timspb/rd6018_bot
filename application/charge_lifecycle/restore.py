"""Restore classification and telemetry continuity guards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .contracts import ChargeLifecycleSnapshot, LifecycleEvent, RestoreKind, RestoreResult, TelemetryState


class LifecycleRestoreClassifier:
    def classify(self, snapshot: ChargeLifecycleSnapshot | None, *, legacy_state: Mapping[str, object] | None = None) -> RestoreResult:
        if snapshot is not None:
            return RestoreResult(RestoreKind.RESUME_EXISTING, snapshot, "validated lifecycle identity is present")
        if legacy_state:
            return RestoreResult(RestoreKind.AMBIGUOUS, None, "legacy state has no validated lifecycle identity")
        return RestoreResult(RestoreKind.START_NEW, None, "no persisted lifecycle snapshot")


class TelemetryContinuityGuard:
    """Stale/missing telemetry preserves phase; it never creates a transition."""

    def evaluate(self, phase: str, telemetry_state: TelemetryState, proposed_phase: str | None) -> str:
        if telemetry_state in {TelemetryState.STALE, TelemetryState.MISSING}:
            return phase
        return proposed_phase or phase


def validate_event_continuity(events: Sequence[LifecycleEvent], session_id: str, trace_id: str) -> tuple[bool, str]:
    if not events:
        return False, "no lifecycle events"
    previous = -1.0
    for event in events:
        if event.session_id != session_id or event.trace_id != trace_id:
            return False, "event identity mismatch"
        if event.timestamp < previous:
            return False, "event order is not monotonic"
        previous = event.timestamp
    return True, "event continuity valid"


__all__ = ["LifecycleRestoreClassifier", "TelemetryContinuityGuard", "validate_event_continuity"]
