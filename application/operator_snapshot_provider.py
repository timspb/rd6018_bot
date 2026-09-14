"""Read-only provider adapting the preserved V1/V2 runtime to V3 UI data."""

from __future__ import annotations

import inspect
import time
from typing import Any, Mapping

from operator_hmi import HmiProcessState, build_operator_hmi_state
from rd6018_telemetry import telemetry_freshness
from runtime.diagnostics import DiagnosticAuthority
from runtime.journal import format_entry
from runtime.ui.models import ChargeView, DiagnosticsView, RuntimeUISnapshot, SafetyView, TelemetryView

from .operator_snapshot import OperatorSnapshot


class OperatorSnapshotProvider:
    """Expose a sanitized snapshot without invoking runtime commands.

    The provider deliberately receives the legacy application object at the
    composition boundary. It reads it and the live HA snapshot only; no method
    that can start/stop charging or write an actuator is called here.
    """

    def __init__(self, app: Any, *, journal: Any = None) -> None:
        self.app = app
        self.journal = journal

    async def get_operator_snapshot(self) -> OperatorSnapshot:
        live = await self.app.hass.get_all_live()
        hmi = build_operator_hmi_state(self.app, live)
        return self._build_snapshot(live, hmi)

    async def get_diagnostics(self) -> DiagnosticsView:
        live = await self.app.hass.get_all_live()
        return self._diagnostics(live)

    async def get_journal(self, limit: int = 20) -> tuple[str, ...]:
        if limit < 0:
            raise ValueError("limit must not be negative")
        recorder = self.journal or getattr(self.app, "journal_recorder", None)
        if recorder is None:
            recorder = getattr(self.app, "journal", None)
        if recorder is None or not callable(getattr(recorder, "tail", None)):
            return ()
        entries = recorder.tail(limit)
        if inspect.isawaitable(entries):
            entries = await entries
        return tuple(format_entry(entry) if hasattr(entry, "short_message") else str(entry) for entry in entries)

    async def submit_intent(self, intent: Any):
        """Fail closed until a command adapter is explicitly wired by a later PR."""
        from runtime.ui.commands.models import CommandResult, CommandStatus

        del intent
        return CommandResult(CommandStatus.REJECTED, "operator_intent_provider_read_only")

    def legacy_hmi_state(self, live: Mapping[str, Any]):
        """Expose the source state for shadow comparison; still read-only."""
        return build_operator_hmi_state(self.app, live)

    @staticmethod
    def hmi_state_from_snapshot(snapshot: OperatorSnapshot):
        """Adapt sanitized V3 data to the preserved renderer's data model."""
        from operator_hmi import HmiAuthority, HmiProcessState, OperatorHmiState

        process = {
            "IDLE": HmiProcessState.IDLE,
            "CHARGING": HmiProcessState.RUNNING,
            "FAULT": HmiProcessState.CONTAINMENT,
        }.get(snapshot.state, HmiProcessState.CONTAINMENT)
        authority = HmiAuthority.AUTO if snapshot.state == "CHARGING" else (
            HmiAuthority.NONE if snapshot.state == "IDLE" else HmiAuthority.CONTAINMENT
        )
        view = snapshot.snapshot
        return OperatorHmiState(
            process_state=process,
            authority=authority,
            title=f"RD6018 · {view.charge.stage}",
            output_on=bool(view.output.get("enabled")),
            regulator=view.charge.phase or "—",
            battery_label=str(view.battery.get("label", "") or ""),
            battery_voltage_v=view.telemetry.voltage,
            current_a=view.telemetry.current,
            power_w=view.output.get("power_w"),
            battery_temp_c=view.telemetry.temperature,
            psu_temp_c=None,
            target_voltage_v=view.charge.targets.get("voltage"),
            current_limit_a=view.charge.targets.get("current"),
            progress=view.charge.waiting_for or "",
            safety=view.safety.reason or ("Защита: норма" if view.safety.allowed else "⚠️ Safety blocked"),
            attention="normal" if view.safety.allowed else "alarm",
            stage_status=str(view.charge.evidence.get("stage_status", "") or ""),
            stage_time=view.charge.timer_text,
            delivered_ah=view.telemetry.accumulated_ah,
        )

    def _build_snapshot(self, live: Mapping[str, Any], hmi: Any) -> OperatorSnapshot:
        fresh = telemetry_freshness(
            live, ("switch", "battery_voltage", "current", "protection_code", "regulation_code")
        ).valid
        state = self._state(hmi, live, fresh)
        stage = str(getattr(getattr(self.app, "charge_controller", None), "current_stage", "") or "")
        if not stage:
            stage = str(getattr(hmi, "title", "IDLE") or "IDLE")
        faults = self._faults(live, hmi)
        diagnostics = self._diagnostics(live, faults=faults)
        safety = SafetyView(
            allowed=not faults and fresh,
            reason="; ".join(faults) if faults else ("telemetry_stale" if not fresh else ""),
            violations=faults,
        )
        charge = ChargeView(
            stage=stage,
            program=str(getattr(hmi, "authority", "") or ""),
            phase=str(getattr(hmi, "regulator", "") or "") or None,
            timer_text=str(getattr(hmi, "stage_time", "") or getattr(hmi, "total_time", "") or ""),
            waiting_for=str(getattr(hmi, "progress", "") or "") or None,
            targets={"voltage": getattr(hmi, "target_voltage_v", None), "current": getattr(hmi, "current_limit_a", None)},
            evidence={"finish": getattr(hmi, "finish_evidence", None), "stage_status": getattr(hmi, "stage_status", "")},
        )
        telemetry = TelemetryView(
            voltage=getattr(hmi, "battery_voltage_v", None),
            current=getattr(hmi, "current_a", None),
            temperature=getattr(hmi, "battery_temp_c", None),
            accumulated_ah=getattr(hmi, "delivered_ah", None),
        )
        runtime_snapshot = RuntimeUISnapshot(
            charge=charge,
            battery={"label": getattr(hmi, "battery_label", "")},
            telemetry=telemetry,
            diagnostics=diagnostics,
            safety=safety,
            output={"enabled": getattr(hmi, "output_on", None), "power_w": getattr(hmi, "power_w", None)},
            journal_tail=(),
        )
        return OperatorSnapshot(
            state=state,
            snapshot=runtime_snapshot,
            available_actions=self._actions(state, fresh, bool(getattr(hmi, "output_on", False))),
            faults=faults,
            telemetry_fresh=fresh,
        )

    @staticmethod
    def _state(hmi: Any, live: Mapping[str, Any], fresh: bool) -> str:
        process = getattr(hmi, "process_state", None)
        if process in {HmiProcessState.RUNNING, HmiProcessState.PAUSED, HmiProcessState.STORAGE, HmiProcessState.ADOPTED_MIX}:
            return "CHARGING"
        if process in {HmiProcessState.CONTAINMENT, HmiProcessState.HANDS_OFF, HmiProcessState.INTERRUPTED} or not fresh:
            return "FAULT"
        if str(getattr(hmi, "attention", "normal")) == "alarm":
            return "FAULT"
        return "IDLE"

    @staticmethod
    def _faults(live: Mapping[str, Any], hmi: Any) -> tuple[str, ...]:
        faults = []
        if str(getattr(hmi, "attention", "normal")) == "alarm":
            faults.append(str(getattr(hmi, "safety", "safety_alarm")))
        if str(live.get("ovp_triggered", "")).lower() in {"on", "true", "1"}:
            faults.append("OVP")
        if str(live.get("ocp_triggered", "")).lower() in {"on", "true", "1"}:
            faults.append("OCP")
        return tuple(dict.fromkeys(faults))

    def _diagnostics(self, live: Mapping[str, Any], *, faults: tuple[str, ...] = ()) -> DiagnosticsView:
        report = next((getattr(self.app, name, None) for name in ("battery_diagnostic_report", "diagnostic_report") if getattr(self.app, name, None) is not None), None)
        decision = getattr(report, "authority", report)
        authority = getattr(decision, "value", decision) or DiagnosticAuthority.ALLOW.value
        reasons = tuple(str(x) for x in (getattr(decision, "reasons", ()) or ()))
        return DiagnosticsView(
            authority=str(authority),
            hypotheses=tuple(str(x) for x in faults),
            reasons=reasons or faults,
        )

    @staticmethod
    def _actions(state: str, fresh: bool, output_on: bool) -> tuple[str, ...]:
        if state == "CHARGING":
            return ("stop_charge", "show_journal", "show_graph", "refresh")
        if state == "IDLE" and fresh and not output_on:
            return ("start_charge", "show_journal", "show_diagnostics", "refresh")
        return ("show_diagnostics", "show_journal", "refresh")
