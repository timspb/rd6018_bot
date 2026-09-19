"""Single read-only V3 observer composition root."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from v3_core.canonical_events import CanonicalTimelineSnapshot

from .active_session_parity import ActiveSessionParityObserver
from .operator_dashboard_composer import OperatorDashboardComposer, OperatorDashboardState
from .operator_explanation import DecisionExplanationEngine
from .operator_runtime_view import OperatorRuntimeViewComposer
from .telegram_operator_adapter import TelegramOperatorViewAdapter


@dataclass(frozen=True)
class ObserverLifecycle:
    started: bool
    shutdown: bool
    degraded_sources: tuple[str, ...] = ()


class V3ObserverComposition:
    """Wire readers/observers/formatters only; no command-capable dependency is accepted."""

    def __init__(self, *, evidence_reader: Callable[[], Mapping[str, Any]] | None = None, telemetry_reader: Callable[[], Mapping[str, Any]] | None = None, diagnostics_reader: Callable[[], tuple[Mapping[str, Any], ...]] | None = None) -> None:
        self._evidence_reader = evidence_reader
        self._telemetry_reader = telemetry_reader
        self._diagnostics_reader = diagnostics_reader
        self._parity = ActiveSessionParityObserver()
        self._runtime_view = OperatorRuntimeViewComposer()
        self._explanations = DecisionExplanationEngine()
        self._dashboard = OperatorDashboardComposer()
        self._telegram = TelegramOperatorViewAdapter()
        self._lifecycle = ObserverLifecycle(False, False)

    @property
    def lifecycle(self) -> ObserverLifecycle:
        return self._lifecycle

    def startup(self) -> ObserverLifecycle:
        if not self._lifecycle.started:
            self._lifecycle = ObserverLifecycle(True, False)
        return self._lifecycle

    def shutdown(self) -> ObserverLifecycle:
        self._lifecycle = ObserverLifecycle(False, True, self._lifecycle.degraded_sources)
        return self._lifecycle

    def snapshot(self, observations: Mapping[str, Any] | None = None) -> OperatorDashboardState:
        observations = dict(observations or {})
        degraded: list[str] = []
        supplied = self._read(self._evidence_reader, "evidence", degraded)
        supplied.update(observations.get("evidence", {}))
        telemetry = self._read(self._telemetry_reader, "telemetry", degraded)
        telemetry.update(observations.get("telemetry", {}))
        if not telemetry:
            telemetry = {"source": "UNKNOWN"}
        diagnostics = self._read(self._diagnostics_reader, "diagnostics", degraded) or tuple(observations.get("diagnostics", ()))
        persisted = observations.get("persisted", supplied.get("persisted", {})) or {}
        telemetry_sources = observations.get("telemetry_sources", supplied.get("telemetry_sources", {}))
        observation = self._parity.ingest(persisted=persisted, telemetry=telemetry, rd=observations.get("rd", telemetry_sources.get("rd", {})), esphome=observations.get("esphome", telemetry_sources.get("esphome", {})), ha=observations.get("ha", telemetry_sources.get("ha", {})))
        v2_state = observations.get("v2_state", {"profile": observation.profile, "phase": observation.phase, "state": observation.state})
        v3_state = observations.get("v3_state", dict(v2_state))
        parity = self._parity.compare(observation, v2_state=v2_state, v3_state=v3_state, diagnostics=diagnostics)
        explanation = self._explanations.explain(observation=observation, parity=parity, evidence=observations.get("explanation", supplied.get("explanation", {})))
        runtime_view = self._runtime_view.compose(observation=observation, parity=parity, timeline=observations.get("timeline"), diagnostics=diagnostics, shadow=observations.get("shadow", supplied.get("shadow", {})), explanation=explanation)
        self._lifecycle = ObserverLifecycle(self._lifecycle.started, self._lifecycle.shutdown, tuple(degraded))
        return self._dashboard.compose(runtime_view=runtime_view, explanation=explanation, canary=observations.get("canary", supplied.get("canary", {})), timestamp=observations.get("timestamp"))

    def telegram_message(self, state: OperatorDashboardState) -> str:
        return self._telegram.format(state)

    @staticmethod
    def _read(reader: Callable[[], Any] | None, name: str, degraded: list[str]) -> dict[str, Any] | tuple[Mapping[str, Any], ...]:
        if reader is None:
            return {}
        try:
            value = reader()
            return value or {}
        except Exception:
            degraded.append(name)
            return {}


__all__ = ["ObserverLifecycle", "V3ObserverComposition"]
