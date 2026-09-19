"""Read-only operator runtime composition for V3 observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from v3_core.canonical_events import CanonicalTimelineSnapshot

from .active_session_parity import ActiveSessionParityEvidence, ActiveSessionObservation
from .operator_state.diagnostics import OperatorDiagnosticsView


@dataclass(frozen=True)
class OperatorRuntimeView:
    mode: str
    control_enabled: bool
    profile: str | None
    phase: str | None
    state: str | None
    voltage: float | None
    current: float | None
    power: float | None
    temperature: float | None
    source: str
    confidence: str
    identity_status: str
    lease_observation: Mapping[str, Any]
    protection_state: Mapping[str, Any]
    stale_indicators: tuple[str, ...]
    comparison: str
    divergence: str | None
    evidence_freshness: float | None
    timeline: CanonicalTimelineSnapshot | None
    diagnostics: OperatorDiagnosticsView
    explanation: Any | None = None
    unknown_reasons: tuple[str, ...] = ()


class OperatorRuntimeViewComposer:
    """Compose presentation data from supplied observations; no command surface."""

    def compose(self, *, observation: ActiveSessionObservation, parity: ActiveSessionParityEvidence, timeline: CanonicalTimelineSnapshot | None = None, diagnostics: Iterable[Mapping[str, Any]] = (), shadow: Mapping[str, Any] | None = None, explanation: Any | None = None) -> OperatorRuntimeView:
        telemetry = observation.telemetry
        shadow = shadow or {}
        stale = tuple(str(item) for item in shadow.get("stale_sources", ()))
        diagnostics_view = self._diagnostics(diagnostics, stale)
        current_timeline = timeline if timeline is not None and timeline.session_id == observation.session_id else None
        power = telemetry.get("power")
        if power is None and telemetry.get("voltage") is not None and telemetry.get("current") is not None:
            power = float(telemetry["voltage"]) * float(telemetry["current"])
        return OperatorRuntimeView(
            mode="OBSERVE",
            control_enabled=False,
            profile=observation.profile,
            phase=observation.phase,
            state=observation.state,
            voltage=telemetry.get("voltage"),
            current=telemetry.get("current"),
            power=power,
            temperature=telemetry.get("temperature"),
            source=str(telemetry.get("source", "supplied observations")),
            confidence=observation.confidence,
            identity_status=observation.identity_status.value,
            lease_observation=dict(shadow.get("lease", {})),
            protection_state=dict(shadow.get("protection", {})),
            stale_indicators=stale,
            comparison=parity.comparison.value,
            divergence=None if parity.comparison.value == "MATCH" else parity.reason,
            evidence_freshness=shadow.get("evidence_freshness"),
            timeline=current_timeline,
            diagnostics=diagnostics_view,
            explanation=explanation,
            unknown_reasons=tuple(getattr(explanation, "unknown_reasons", ())),
        )

    @staticmethod
    def _diagnostics(records: Iterable[Mapping[str, Any]], stale: tuple[str, ...]) -> OperatorDiagnosticsView:
        warnings: list[str] = []
        blockers: list[str] = []
        ambiguities: list[str] = []
        for record in records:
            message = str(record.get("message") or record.get("reason") or record.get("code") or "diagnostic")
            severity = str(record.get("severity", "warning")).lower()
            if severity in {"critical", "error", "blocker"}:
                blockers.append(message)
            elif severity in {"warning", "warn"}:
                warnings.append(message)
            if record.get("ambiguous"):
                ambiguities.append(message)
        return OperatorDiagnosticsView(tuple(warnings), tuple(blockers), stale, tuple(ambiguities))


__all__ = ["OperatorDiagnosticsView", "OperatorRuntimeView", "OperatorRuntimeViewComposer"]
