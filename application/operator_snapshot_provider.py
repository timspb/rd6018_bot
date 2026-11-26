"""Read-only provider adapting the preserved V1/V2 runtime to V3 UI data."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from runtime.ui.models import (
    ChargeView,
    DiagnosticsView,
    EntityStatusItem,
    EntityStatusView,
    JournalView,
    RuntimeUISnapshot,
    SafetyView,
    TelemetryView,
)

from .journal_read_service import EventJournalReadService
from .operator_read_source import DiagnosticAuthority, HmiProcessState, OperatorReadSource
from .operator_snapshot import OperatorSnapshot
from .operator_views import OperatorDetailsView, ServiceDetailsView
from .operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from .intents import IntentDispatcher, OperatorIntent


def build_legacy_ai_context_text(
    live: Mapping[str, Any],
    controller: Mapping[str, Any],
    *,
    safe_float,
    canonical_bool,
    format_snapshot,
    format_events,
    strategy_snapshot: Mapping[str, Any],
    strategy_events,
) -> str:
    """Render the legacy Russian AI snapshot from already-read facts only."""
    v_out = safe_float(live.get("voltage", 0.0))
    i_out = safe_float(live.get("current", 0.0))
    p_out = safe_float(live.get("power", 0.0))
    v_batt = safe_float(live.get("battery_voltage", 0.0))
    ah = safe_float(live.get("ah", 0.0))
    wh = safe_float(live.get("wh", 0.0))
    v_set = safe_float(live.get("set_voltage", 0.0))
    i_set = safe_float(live.get("set_current", 0.0))
    ovp = safe_float(live.get("ovp", 0.0))
    ocp = safe_float(live.get("ocp", 0.0))
    output_on = str(live.get("switch", "")).lower() == "on"
    cv_mode = canonical_bool(live, "is_cv")
    cc_mode = canonical_bool(live, "is_cc")
    t_internal = safe_float(live.get("temp_int", 0.0))
    t_external = safe_float(live.get("temp_ext", 0.0))
    v_input = safe_float(live.get("input_voltage", 0.0)) or 0.0
    uptime = live.get("uptime", "неизвестно")

    capacity_ah = controller.get("capacity_ah", 0)
    capacity_known = bool(controller.get("is_active")) and int(capacity_ah or 0) > 0
    controller_info = ""
    if controller.get("is_active"):
        timers = controller.get("timers") or {}
        controller_info = f"""
Контроллер заряда:
- Активный этап: {controller.get('stage')}
- Тип АКБ: {controller.get('battery_type')}
- Заданная емкость: {capacity_ah}Ач
- Общее время: {timers['total_time']}
- Время этапа: {timers['stage_time']}
- Лимит этапа: {timers['remaining_time']}"""

    controller_info += f"""

Карточка стратегии:
{format_snapshot(strategy_snapshot)}"""
    if strategy_events:
        controller_info += f"""

Последние важные события:
{format_events(strategy_events, limit=8)}"""
    context = f"""ПОЛНЫЙ СЛЕПОК RD6018:

Статус выхода: {"ON" if output_on else "OFF"} (включен/выключен)
Емкость известна: {"да" if capacity_known else "нет"}
Емкость АКБ: {capacity_ah if capacity_known else "UNKNOWN"} Ач

Электрика:
- Напряжение на выходе: {v_out:.3f}В
- Ток нагрузки: {i_out:.3f}А
- Мощность: {p_out:.2f}Вт
- Напряжение на клеммах АКБ: {v_batt:.3f}В

Счетчики:
- Накопленная емкость: {ah:.3f} Ач
- Накопленная энергия: {wh:.2f} Вч

Уставки:
- Целевое напряжение: {v_set:.2f}В
- Лимит тока: {i_set:.2f}А
- Защита перенапряжения: {ovp:.1f}В
- Защита перетока: {ocp:.1f}А

Статусы:
- Выход включен: {'да' if output_on else 'нет'}
- Режим стабилизации напряжения: {'да' if cv_mode else 'нет'}
- Режим стабилизации тока: {'да' if cc_mode else 'нет'}
- Режим измерения АКБ: {'да' if not output_on else 'нет'}

Температура:
- Температура блока: {t_internal:.1f}°C
- Температура АКБ: {t_external:.1f}°C

Система:
- Входное напряжение БП: {v_input:.1f}В
- Время работы: {uptime}{controller_info}"""
    return context


def append_legacy_ai_log_events(context: str, events) -> str:
    """Append the separate legacy five-event window to rendered context."""
    if not events:
        return context
    context += "\n\nПоследние события из лога:\n"
    for event in events:
        context += f"- {event}\n"
    return context


def build_legacy_ai_context_dict(
    live: Mapping[str, Any],
    controller: Mapping[str, Any],
    strategy_snapshot: Mapping[str, Any],
    *,
    safe_float,
) -> dict[str, Any]:
    """Assemble the legacy UNKNOWN-safe AI shape from read-only facts."""
    unknown: dict[str, Any] = {
        "output_status": "UNKNOWN",
        "current_stage": "UNKNOWN",
        "battery_type": "UNKNOWN",
        "mode": "UNKNOWN",
        "capacity_ah": "UNKNOWN",
        "capacity_known": False,
        "remaining_time": "—",
        "v_batt_now": None,
        "i_now": None,
        "temp_ext_now": None,
        "temp_int_now": None,
    }
    capacity = controller.get("capacity_ah") or 0
    capacity_known = float(capacity) > 0
    timers = strategy_snapshot.get("timers") or {}
    return {
        **unknown,
        "output_status": "ON" if str(live.get("switch", "")).lower() == "on" else "OFF",
        "current_stage": strategy_snapshot.get("stage", controller.get("stage", "UNKNOWN")),
        "battery_type": strategy_snapshot.get("profile", controller.get("battery_type", "UNKNOWN")),
        "mode": strategy_snapshot.get("phase", "UNKNOWN"),
        "capacity_ah": int(capacity) if capacity_known else "UNKNOWN",
        "capacity_known": capacity_known,
        "remaining_time": timers.get("remaining_time", "—"),
        "v_batt_now": safe_float(live.get("battery_voltage")),
        "i_now": safe_float(live.get("current")),
        "temp_ext_now": safe_float(live.get("temp_ext")),
        "temp_int_now": safe_float(live.get("temp_int")),
    }


class OperatorSnapshotProvider:
    """Expose sanitized operator views from an explicit read source.

    The provider never receives the production runtime object and never creates
    command handlers.  Composition supplies the read-only source and, when
    mutation intents are enabled, a pre-built dispatcher.
    """

    def __init__(
        self,
        source: OperatorReadSource,
        *,
        intent_dispatcher: IntentDispatcher | None = None,
        event_journal_reader: EventJournalReadService | None = None,
    ) -> None:
        if not isinstance(source, OperatorReadSource):
            raise TypeError("OperatorSnapshotProvider requires OperatorReadSource")
        self._source = source
        self._event_journal_reader = event_journal_reader or EventJournalReadService()
        self.intent_dispatcher = intent_dispatcher or IntentDispatcher()

    async def get_operator_snapshot(self) -> OperatorSnapshot:
        live = await self._source.read_live()
        hmi = self._source.hmi_state(live)
        return self._build_snapshot(live, hmi)

    async def get_diagnostics(self) -> DiagnosticsView:
        live = await self._source.read_live()
        return self._diagnostics(live)

    async def get_operator_details(self) -> OperatorDetailsView:
        live = await self._source.read_live()
        hmi = self._source.hmi_state(live)
        controller = self._source.controller()
        timers = {}
        if controller is not None and bool(getattr(controller, "is_active", False)):
            try:
                timers = dict(controller.get_timers() or {})
            except Exception:
                timers = {}
        request = self._source.manual_request()
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
            observer_status=str(getattr(self._source.observer(), "last_status", "") or ""),
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
        live = await self._source.read_live()
        hmi = self._source.hmi_state(live)
        controller = self._source.controller()
        snapshot = {}
        if controller is not None:
            try:
                snapshot = dict(controller.ui_support_snapshot() or {})
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

    async def get_operator_actions(self, *, snapshot: OperatorSnapshot | None = None) -> OperatorActionsView:
        # Reuse the complete home read model for every state.  A second live
        # read can otherwise change ownership between the text and keyboard;
        # HANDS_OFF must never be remapped to a safety fault in that gap.
        if snapshot is not None:
            if snapshot.state == "HANDS_OFF":
                output_on = bool(snapshot.snapshot.output.get("enabled"))
                if output_on:
                    return self._actions(
                        (OperatorAction.ADOPT_MIX, OperatorAction.DISABLE_OUTPUT),
                        (),
                        "hands_off",
                    )
                return self._actions(
                    (OperatorAction.START_CHARGE, OperatorAction.RETURN_PB_CONTROL),
                    (OperatorAction.SELECT_PROFILE,),
                    "hands_off",
                )
            return OperatorActionsView.for_state(
                snapshot.state,
                safety_allowed=snapshot.snapshot.safety.allowed,
                pause_allowed=False,
            )

        live = await self._source.read_live()
        hmi = self._source.hmi_state(live)
        if hmi.process_state is HmiProcessState.ADOPTED_MIX:
            available = (OperatorAction.STOP_MIX, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE), "adopted_mix")
        if hmi.process_state is HmiProcessState.INTERRUPTED:
            available = (OperatorAction.ADOPT_MIX, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (OperatorAction.START_CHARGE, OperatorAction.STOP_CHARGE), "interrupted")
        if hmi.process_state is HmiProcessState.HANDS_OFF:
            available = (OperatorAction.ADOPT_MIX, OperatorAction.DISABLE_OUTPUT) if hmi.output_on else (OperatorAction.START_CHARGE, OperatorAction.RETURN_PB_CONTROL)
            return self._actions(available, (), "hands_off")
        if hmi.process_state is HmiProcessState.STORAGE:
            return self._actions((OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS), (OperatorAction.START_CHARGE, OperatorAction.STOP_CHARGE), "storage")
        if hmi.process_state in {HmiProcessState.RUNNING, HmiProcessState.PAUSED} and hmi.authority.value in {"auto", "manual"}:
            paused = self._source.pause_active()
            available = (OperatorAction.RESUME_CHARGE if paused else OperatorAction.PAUSE_CHARGE, OperatorAction.STOP_CHARGE, OperatorAction.SHOW_LOG, OperatorAction.SHOW_GRAPH, OperatorAction.SHOW_DIAGNOSTICS)
            return self._actions(available, (OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE), "charging")
        snapshot = self._build_snapshot(live, hmi)
        return OperatorActionsView.for_state(snapshot.state, safety_allowed=snapshot.snapshot.safety.allowed, pause_allowed=False)

    @staticmethod
    def _actions(available, disabled, reason: str) -> OperatorActionsView:
        reasons = {action.value: reason for action in disabled}
        return OperatorActionsView(tuple(OperatorActionSpec(action) for action in available), tuple(disabled), reasons)

    def _observer_state(self) -> str:
        observer = self._source.observer()
        raw = getattr(observer, "state", "") if observer is not None else ""
        return str(getattr(raw, "value", raw) or "")

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    async def get_event_journal(self, limit: int | None = 50) -> JournalView:
        return await self._event_journal_reader.aread(limit)

    async def get_entity_statuses(self) -> EntityStatusView:
        try:
            rows = await self._source.read_entities_status()
        except Exception as exc:
            return EntityStatusView(error=f"{type(exc).__name__}: {exc}")
        items = tuple(
            EntityStatusItem(
                key=str(row.get("key") or ""),
                state=row.get("state"),
                status=str(row.get("status") or "unknown"),
                unit=str(row.get("unit") or ""),
                friendly_name=str(row.get("friendly_name") or ""),
            )
            for row in rows
        )
        return EntityStatusView(items=items)

    async def get_journal(self, limit: int = 20) -> tuple[str, ...]:
        if limit < 0:
            raise ValueError("limit must not be negative")
        recorder = self._source.journal()
        if recorder is None or not callable(getattr(recorder, "tail", None)):
            return ()
        entries = recorder.tail(limit)
        if inspect.isawaitable(entries):
            entries = await entries
        return tuple(self._source.format_journal_entry(entry) for entry in entries)

    async def submit_intent(self, intent: Any):
        """Route read-only intents; execution intents remain unmigrated."""
        from runtime.ui.commands.models import CommandResult, CommandStatus

        if not isinstance(intent, OperatorIntent):
            return CommandResult(CommandStatus.REJECTED, "invalid_operator_intent")
        return await self.intent_dispatcher.dispatch(intent)

    @staticmethod
    def hmi_state_from_snapshot(snapshot: OperatorSnapshot):
        """Adapt sanitized V3 data to the preserved renderer's data model."""
        return OperatorReadSource.hmi_from_snapshot(snapshot)

    def _build_snapshot(self, live: Mapping[str, Any], hmi: Any) -> OperatorSnapshot:
        fresh = self._source.freshness(live, ("switch", "battery_voltage", "current", "protection_code", "regulation_code"))
        state = self._state(hmi, live, fresh)
        stage = str(getattr(self._source.controller(), "current_stage", "") or "")
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
        if process is HmiProcessState.HANDS_OFF:
            return "HANDS_OFF"
        if process in {HmiProcessState.CONTAINMENT, HmiProcessState.INTERRUPTED} or not fresh:
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
        report = next((self._source.get(name) for name in ("battery_diagnostic_report", "diagnostic_report") if self._source.get(name) is not None), None)
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
        if state == "HANDS_OFF":
            return (("adopt_mix", "disable_output") if output_on else ("start_charge", "return_pb_control", "refresh"))
        if state == "IDLE" and fresh and not output_on:
            return ("start_charge", "show_journal", "show_diagnostics", "refresh")
        return ("show_diagnostics", "show_journal", "refresh")
