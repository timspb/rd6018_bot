"""Single-snapshot, read-only operator dashboard composition."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any, Mapping

from .operator_explanation import OperatorExplanation
from .operator_state import OperatorDiagnosticsView
from .charge_lifecycle import ChargeLifecycleSnapshot
from .operator_timeline import CanonicalOperatorTimeline
from .operator_state import OperatorStateSnapshot
from v3_core.canonical_events import CanonicalChargeEvent


@dataclass(frozen=True)
class CurrentSessionPanel:
    profile: str | None
    phase: str | None
    state: str | None
    identity_status: str


@dataclass(frozen=True)
class TimelinePanel:
    session_id: str | None
    event_count: int
    graph_reset: bool
    fake_lifecycle: bool
    events: tuple[object, ...] = ()


@dataclass(frozen=True)
class TelemetryPanel:
    voltage: float | None
    current: float | None
    power: float | None
    temperature: float | None
    source: str
    confidence: str
    stale_indicators: tuple[str, ...]


@dataclass(frozen=True)
class SafetyPanel:
    lease: Mapping[str, Any]
    protection: Mapping[str, Any]
    stale: tuple[str, ...]


@dataclass(frozen=True)
class ParityPanel:
    status: str
    divergence: str | None


@dataclass(frozen=True)
class CanaryPanel:
    status: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class OperatorDashboardState:
    timestamp: float
    current_session: CurrentSessionPanel
    timeline: TimelinePanel
    telemetry: TelemetryPanel
    explanation: OperatorExplanation | None
    safety: SafetyPanel
    diagnostics: OperatorDiagnosticsView
    parity: ParityPanel
    canary: CanaryPanel
    observe_only: bool = True


class OperatorDashboardComposer:
    """Compose panels from one canonical operator state and timeline."""

    def compose(self, *, state: OperatorStateSnapshot | None = None, timeline: CanonicalOperatorTimeline | None = None, runtime_view: Any | None = None, explanation: OperatorExplanation | None = None, canary: Mapping[str, Any] | None = None, timestamp: float | None = None, lifecycle: ChargeLifecycleSnapshot | None = None, events: tuple[CanonicalChargeEvent, ...] = ()) -> OperatorDashboardState:
        if state is None and runtime_view is None:
            raise TypeError("OperatorStateSnapshot or canonical runtime input is required")
        canary = canary or {}
        runtime_timeline = getattr(runtime_view, "timeline", None) if runtime_view is not None else None
        operator_timeline = timeline or (CanonicalOperatorTimeline.from_sources(lifecycle, events, runtime_timeline) if lifecycle is not None else None)
        timeline_panel = TimelinePanel(
            operator_timeline.session_id if operator_timeline else (runtime_timeline.session_id if runtime_timeline else "UNKNOWN"),
            len(operator_timeline.events) if operator_timeline else (len(runtime_timeline.ordered_events) if runtime_timeline else 0),
            True,
            False,
            operator_timeline.events if operator_timeline else (),
        )
        telemetry = TelemetryPanel(
            state.telemetry.voltage_v if state else runtime_view.voltage,
            state.telemetry.current_a if state else runtime_view.current,
            state.telemetry.power_w if state else runtime_view.power,
            state.telemetry.temperature_c if state else runtime_view.temperature,
            state.telemetry.freshness if state else runtime_view.source,
            state.safety.confidence if state else runtime_view.confidence,
            (state.safety.stale_state,) if state else runtime_view.stale_indicators,
        )
        canary_status = str(canary.get("status", "UNKNOWN"))
        blockers = tuple(str(item) for item in canary.get("blockers", ()))
        return OperatorDashboardState(
            float(timestamp if timestamp is not None else time()),
            CurrentSessionPanel(state.battery_profile if state else runtime_view.profile, state.current_phase if state else runtime_view.phase, state.phase_state.value if state else runtime_view.state, state.lifecycle_status if state else runtime_view.identity_status),
            timeline_panel,
            telemetry,
            explanation if explanation is not None else (state.explanation if state else runtime_view.explanation),
            SafetyPanel({} if state else runtime_view.lease_observation, {"state": state.safety.protection_state} if state else runtime_view.protection_state, (state.safety.stale_state,) if state else runtime_view.stale_indicators),
            runtime_view.diagnostics if runtime_view is not None else OperatorDiagnosticsView((), (), (), ()),
            ParityPanel("UNKNOWN" if state else runtime_view.comparison, None if state else runtime_view.divergence),
            CanaryPanel(canary_status, blockers),
            True,
        )


__all__ = ["CurrentSessionPanel", "TimelinePanel", "TelemetryPanel", "SafetyPanel", "ParityPanel", "CanaryPanel", "OperatorDashboardState", "OperatorDashboardComposer"]
