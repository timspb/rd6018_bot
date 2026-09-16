"""Read-only provider adapting the preserved V1/V2 runtime to V3 UI data."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from runtime.ui.models import ChargeView, DiagnosticsView, RuntimeUISnapshot, SafetyView, TelemetryView

from .operator_observation_source import DiagnosticAuthority, HmiProcessState, OperatorObservationSource
from .operator_snapshot import OperatorSnapshot
from .operator_views import OperatorDetailsView, ServiceDetailsView
from .operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from .intents import IntentDispatcher, OperatorIntent, OperatorIntentKind
from .stop_command import StopCommandHandler
from .pause_command import PauseCommandHandler
from .profile_command import ProfileCommandHandler


class OperatorSnapshotProvider:
    """Expose a sanitized snapshot without invoking runtime commands.

    The provider deliberately receives the legacy application object at the
    composition boundary. It reads it and the live HA snapshot only; no method
    that can start/stop charging or write an actuator is called here.
    """

    def __init__(self, app: Any, *, journal: Any = None, intent_dispatcher: IntentDispatcher | None = None) -> None:
        self._observation = OperatorObservationSource(app, journal=journal)
        if intent_dispatcher is None:
            pause_handler = PauseCommandHandler().route
            profile_handler = ProfileCommandHandler().route
            intent_dispatcher = IntentDispatcher(
                stop_handler=StopCommandHandler().route,
                routes={
                    OperatorIntentKind.PAUSE_CHARGE: pause_handler,
                    OperatorIntentKind.RESUME_CHARGE: pause_handler,
                    OperatorIntentKind.SELECT_CHARGE_PROFILE: profile_handler,
                },
            )
        self.intent_dispatcher = intent_dispatcher

    async def get_operator_snapshot(self) -> OperatorSnapshot:
        live = await self._observation.read_live()
        hmi = self._observation.hmi_state(live)
        return self._build_snapshot(live, hmi)

    async def get_diagnostics(self) -> DiagnosticsView:
        live = await self._observation.read_live()
        return self._diagnostics(live)

    async def get_operator_details(self) -> OperatorDetailsView:
        live = await self._observation.read_live()
        hmi = self._observation.hmi_state(live)
        controller = self._observation.controller()
        timers = {}
        if controller is not None and bool(getattr(controller, "is_active", False)):
            try:
                timers = dict(controller.get_timers() or {})
            except Exception:
                timers = {}
        request = self._observation.manual_request()
        return OperatorDetailsView(
            process_state=hmi.process_state.value,
            authority=hmi.authority.value,
            output_on=bool(hmi.output_on),
            regulator=hmi.regulator,
            battery_label=hmi.battery_label,
            battery_voltage_v=hmi.battery_voltage_v,
            current_a=hmi.current_a,
            battery_temp_c=hmi.battery_temp_c,
            psu_temp_c=hmi.psu_temp_c,
            target_voltage_v=hmi.target_voltage_v,
            current_limit_a=hmi.current_limit_a,
            safety=hmi.safety,
            progress=hmi.progress,
            observer_state=self._observer_state(),
            observer_status=str(getattr(self._observation.observer(), "last_status", "") or ""),
            stage=str(getattr(controller, "current_stage", "") or ""),
            battery_type=str(getattr(controller, "battery_type", "") or ""),
            capacity_ah=self._number(getattr(controller, "ah_capacity", None)),
            stage_time=str(timers.get("stage_time", hmi.stage_time or "—")),
            total_time=str(timers.get("total_time", hmi.total_time or "—")),
            remaining_time=str(timers.get("remaining_time", "—")),
            delivered_ah=hmi.delivered_ah if hmi.delivered_ah is not None else self._number(live.get("ah")),
            input_voltage_v=self._number(live.get("input_voltage")),
            uptime=str(live.get("uptime") or "—"),
            manual_capacity_ah=self._number(getattr(request, "capacity_ah", None)),
        )

    async def get_service_details(self) -> ServiceDetailsView:
        live = await self._observation.read_live()
        hmi = self._observation.hmi_state(live)
        controller = self._observation.controller()
        snapshot = {}
        if controller is not None:
            try:
                snapshot = dict(controller.v2_ui_snapshot() or {})
            except Exception:
                snapshot = {}
        return ServiceDetailsView(
            authority=hmi.authority.value,
            output_on=bool(hmi.output_on),
            regulator=hmi.regulator,
            stage=str(getattr(controller, "current_stage", "—") or "—"),
            v2_analysis="available" if snapshot.get("runtime_analysis_available") else "unavailable",
            decision=str(snapshot.get("decision") or "—"),
            ovp_v=self._number(live.get("ovp")),
            ocp_a=self._number(live.get("ocp")),
            protection=str(live.get("protection_code") or "—"),
            regulation=str(live.get("regulation_code") or "—"),
            heartbeat=str(live.get("last_reported") or live.get("last_updated") or "—"),
        )

    async def get_operator_actions(self) -> OperatorActionsView:
        live = await self._observation.read_live()
        hmi = self._observation.hmi_state(live)
        if hmi.process_state is HmiProcessState.ADOPTED_MIX:
            available = (OperatorAction.STOP_MIX, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE), "adopted_mix")
        if hmi.process_state is HmiProcessState.INTERRUPTED:
            available = (OperatorAction.ADOPT_MIX, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (OperatorAction.START_CHARGE, OperatorAction.STOP_CHARGE), "interrupted")
        if hmi.process_state is HmiProcessState.HANDS_OFF:
            available = (OperatorAction.ADOPT_MIX, OperatorAction.DISABLE_OUTPUT) if hmi.output_on else (OperatorAction.SELECT_PROFILE, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (), "hands_off")
        if hmi.process_state is HmiProcessState.STORAGE:
            return self._actions((OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS), (OperatorAction.START_CHARGE, OperatorAction.STOP_CHARGE), "storage")
        if hmi.process_state in {HmiProcessState.RUNNING, HmiProcessState.PAUSED} and hmi.authority.value in {"auto", "manual"}:
            paused = self._observation.pause_active()
            available = (OperatorAction.RESUME_CHARGE if paused else OperatorAction.PAUSE_CHARGE, OperatorAction.STOP_CHARGE, OperatorAction.SHOW_LOG, OperatorAction.SHOW_GRAPH, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE), "charging")
        snapshot = self._build_snapshot(live, hmi)
        return OperatorActionsView.for_state(snapshot.state, safety_allowed=snapshot.snapshot.safety.allowed, pause_allowed=False)

    @staticmethod
    def _actions(available, disabled, reason: str) -> OperatorActionsView:
        reasons = {action.value: reason for action in disabled}
        return OperatorActionsView(tuple(OperatorActionSpec(action) for action in available), tuple(disabled), reasons)

    def _observer_state(self) -> str:
        observer = self._observation.observer()
        raw = getattr(observer, "state", "") if observer is not None else ""
        return str(getattr(raw, "value", raw) or "")

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    async def get_journal(self, limit: int = 20) -> tuple[str, ...]:
        if limit < 0:
            raise ValueError("limit must not be negative")
        recorder = self._observation.journal()
        if recorder is None or not callable(getattr(recorder, "tail", None)):
            return ()
        entries = recorder.tail(limit)
        if inspect.isawaitable(entries):
            entries = await entries
        return tuple(self._observation.format_journal_entry(entry) for entry in entries)

    async def submit_intent(self, intent: Any):
        """Route read-only intents; execution intents remain unmigrated."""
        from runtime.ui.commands.models import CommandResult, CommandStatus

        if not isinstance(intent, OperatorIntent):
            return CommandResult(CommandStatus.REJECTED, "invalid_operator_intent")
        return await self.intent_dispatcher.dispatch(intent)

    def legacy_hmi_state(self, live: Mapping[str, Any]):
        """Expose the source state for shadow comparison; still read-only."""
        return self._observation.hmi_state(live)

    @staticmethod
    def hmi_state_from_snapshot(snapshot: OperatorSnapshot):
        """Adapt sanitized V3 data to the preserved renderer's data model."""
        return OperatorObservationSource.hmi_from_snapshot(snapshot)

    def _build_snapshot(self, live: Mapping[str, Any], hmi: Any) -> OperatorSnapshot:
        fresh = self._observation.freshness(live, ("switch", "battery_voltage", "current", "protection_code", "regulation_code"))
        state = self._state(hmi, live, fresh)
        stage = str(getattr(self._observation.controller(), "current_stage", "") or "")
        if not stage:
            stage = str(getattr(hmi, "title", "IDLE") or "IDLE")
        faults = self._faults(live, hmi)
        diagnostics = self._diagnostics(live, faults=faults)
        safety = SafetyView(
            allowed=not faults and fresh,
            reason="; ".join(faults) if faults else ("telemetry_stale" if not fresh else ""),
            violations=faults,
        )
        authority = getattr(hmi, "authority", "")
        authority = getattr(authority, "value", authority)
        charge = ChargeView(
            stage=stage,
            program=str(authority or ""),
            phase=str(getattr(hmi, "regulator", "") or "") or None,
            timer_text=str(getattr(hmi, "stage_time", "") or getattr(hmi, "total_time", "") or ""),
            waiting_for=(
                str(getattr(hmi, "progress", "") or "") or None
                if authority != "manual"
                else None
            ),
            targets={"voltage": getattr(hmi, "target_voltage_v", None), "current": getattr(hmi, "current_limit_a", None)},
            evidence={"finish": getattr(hmi, "finish_evidence", None), "stage_status": getattr(hmi, "stage_status", "")},
        )
        telemetry = TelemetryView(
            voltage=getattr(hmi, "battery_voltage_v", None),
            current=getattr(hmi, "current_a", None),
            temperature=getattr(hmi, "battery_temp_c", None),
            psu_temperature=getattr(hmi, "psu_temp_c", None),
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
            available_actions=self._snapshot_actions(state, fresh, bool(getattr(hmi, "output_on", False))),
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
        report = next((self._observation.get(name) for name in ("battery_diagnostic_report", "diagnostic_report") if self._observation.get(name) is not None), None)
        decision = getattr(report, "authority", report)
        authority = getattr(decision, "value", decision) or DiagnosticAuthority.ALLOW.value
        reasons = tuple(str(x) for x in (getattr(decision, "reasons", ()) or ()))
        return DiagnosticsView(
            authority=str(authority),
            hypotheses=tuple(str(x) for x in faults),
            reasons=reasons or faults,
        )

    @staticmethod
    def _snapshot_actions(state: str, fresh: bool, output_on: bool) -> tuple[str, ...]:
        if state == "CHARGING":
            return ("stop_charge", "show_journal", "show_graph", "refresh")
        if state == "IDLE" and fresh and not output_on:
            return ("start_charge", "show_journal", "show_diagnostics", "refresh")
        return ("show_diagnostics", "show_journal", "refresh")
