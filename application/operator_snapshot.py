"""Application-owned, serializable operator snapshot mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from runtime.ui.models import ChargeView, DiagnosticsView, RuntimeUISnapshot, SafetyView, TelemetryView


class SnapshotSource(Protocol):
    def __call__(self) -> RuntimeUISnapshot: ...


@dataclass(frozen=True)
class OperatorSnapshot:
    """Stable facade value; contains no runtime, transport, or hardware objects."""

    state: str
    snapshot: RuntimeUISnapshot
    available_actions: tuple[str, ...] = ()
    faults: tuple[str, ...] = ()
    telemetry_fresh: bool = True


def snapshot_from_mapping(data: Mapping[str, Any]) -> OperatorSnapshot:
    charge_data = data.get("charge", {})
    telemetry_data = data.get("telemetry", {})
    diagnostics_data = data.get("diagnostics", {})
    safety_data = data.get("safety", {})
    charge = ChargeView(
        stage=str(charge_data.get("stage", "IDLE")),
        program=str(charge_data.get("program", "")),
        phase=charge_data.get("phase"),
        timer_text=str(charge_data.get("timer_text", "")),
        waiting_for=charge_data.get("waiting_for"),
        targets=dict(charge_data.get("targets", {})),
        active_limits=dict(charge_data.get("active_limits", {})),
        evidence=dict(charge_data.get("evidence", {})),
    )
    snapshot = RuntimeUISnapshot(
        charge=charge,
        battery=dict(data.get("battery", {})),
        telemetry=TelemetryView(
            voltage=telemetry_data.get("voltage"),
            current=telemetry_data.get("current"),
            temperature=telemetry_data.get("temperature"),
            psu_temperature=telemetry_data.get("psu_temperature"),
            accumulated_ah=telemetry_data.get("accumulated_ah"),
        ),
        diagnostics=DiagnosticsView(
            authority=str(diagnostics_data.get("authority", "allow")),
            hypotheses=tuple(str(x) for x in diagnostics_data.get("hypotheses", ())),
            reasons=tuple(str(x) for x in diagnostics_data.get("reasons", ())),
        ),
        safety=SafetyView(
            allowed=bool(safety_data.get("allowed", True)),
            reason=str(safety_data.get("reason", "")),
            violations=tuple(str(x) for x in safety_data.get("violations", ())),
        ),
        output=dict(data.get("output", {})),
        journal_tail=tuple(str(x) for x in data.get("journal_tail", ())),
    )
    faults = tuple(str(x) for x in data.get("faults", diagnostics_data.get("faults", ())))
    return OperatorSnapshot(
        state=str(data.get("state", "IDLE")),
        snapshot=snapshot,
        available_actions=tuple(str(x) for x in data.get("available_actions", ())),
        faults=faults,
        telemetry_fresh=bool(data.get("telemetry_fresh", True)),
    )
