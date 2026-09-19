"""Controlled read-only observation-run contracts; no external I/O or writes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .hardware_validation import RealObservation, ShadowComparisonResult


class ObservationRunStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ObservationSession:
    observation_id: str
    started_at: float
    ended_at: float | None
    v2_owner: str
    v3_status: str
    source_availability: Mapping[str, bool]
    status: ObservationRunStatus


@dataclass(frozen=True)
class UiObservation:
    session_starts_from_zero: bool
    graph_reset: bool
    timeline_events_visible: bool
    stale_history_absent: bool
    diagnostics_visible: bool


@dataclass(frozen=True)
class ObservationEvidenceBundle:
    metadata: ObservationSession
    telemetry: tuple[RealObservation, ...] = ()
    state_snapshots: tuple[Mapping[str, Any], ...] = ()
    external_snapshots: tuple[Mapping[str, Any], ...] = ()
    timeline: tuple[Mapping[str, Any], ...] = ()
    divergences: tuple[ShadowComparisonResult, ...] = ()
    diagnostics: tuple[Mapping[str, Any], ...] = ()
    health_snapshots: tuple[Mapping[str, Any], ...] = ()
    ui_observation: UiObservation | None = None


class LiveShadowObservationRun:
    """Collects caller-supplied evidence in memory and cannot control hardware."""

    def __init__(self, session: ObservationSession) -> None:
        if session.status is not ObservationRunStatus.OPEN:
            raise ValueError("observation must start OPEN")
        self._metadata = session
        self._telemetry: list[RealObservation] = []
        self._state: list[Mapping[str, Any]] = []
        self._external: list[Mapping[str, Any]] = []
        self._timeline: list[Mapping[str, Any]] = []
        self._divergences: list[ShadowComparisonResult] = []
        self._diagnostics: list[Mapping[str, Any]] = []
        self._health: list[Mapping[str, Any]] = []
        self._ui: UiObservation | None = None

    def add_telemetry(self, observation: RealObservation) -> None:
        self._telemetry.append(observation)

    def add_state(self, snapshot: Mapping[str, Any]) -> None:
        self._state.append(dict(snapshot))

    def add_external(self, snapshot: Mapping[str, Any]) -> None:
        self._external.append(dict(snapshot))

    def add_timeline_event(self, event: Mapping[str, Any]) -> None:
        self._timeline.append(dict(event))

    def add_divergence(self, result: ShadowComparisonResult) -> None:
        self._divergences.append(result)

    def add_diagnostic(self, diagnostic: Mapping[str, Any]) -> None:
        self._diagnostics.append(dict(diagnostic))

    def add_health(self, health: Mapping[str, Any]) -> None:
        self._health.append(dict(health))

    def set_ui_observation(self, observation: UiObservation) -> None:
        self._ui = observation

    def close(self, ended_at: float, *, blocked: bool = False) -> ObservationEvidenceBundle:
        status = ObservationRunStatus.BLOCKED if blocked else ObservationRunStatus.CLOSED
        metadata = ObservationSession(self._metadata.observation_id, self._metadata.started_at, ended_at, self._metadata.v2_owner, self._metadata.v3_status, dict(self._metadata.source_availability), status)
        return ObservationEvidenceBundle(metadata, tuple(self._telemetry), tuple(self._state), tuple(self._external), tuple(self._timeline), tuple(self._divergences), tuple(self._diagnostics), tuple(self._health), self._ui)


__all__ = ["ObservationRunStatus", "ObservationSession", "UiObservation", "ObservationEvidenceBundle", "LiveShadowObservationRun"]
