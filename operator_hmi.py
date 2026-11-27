from __future__ import annotations

import asyncio
import html
import math
import re
import time
from dataclasses import replace
from typing import Any, Mapping, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from manual_mode import MANUAL_MIX_FINISH_HOLD_SEC
from rd_live_adoption import MIX_FINISH_HOLD_S
from runtime.ui.labels.operator_actions import OPERATOR_ACTION_LABELS
from runtime.ui.components.manual_extrema_progress import _manual_extrema_status
from runtime.ui.components.adopted_mix_progress import _observer_progress
from runtime.ui.components.hmi_battery_identity import _battery_label_from_manual, _battery_label_from_observer
from runtime.ui.components.hmi_live_safety import _normal_safety, _operator_telemetry_fresh, _protection_tripped
from runtime.ui.hmi_layout_config import PANEL_HEADING_TARGET_WIDTH, PANEL_HEADING_MIN_GAP
from runtime.ui.components.hmi_state import (
    HmiProcessState, HmiAuthority, OperatorHmiState,
    project_managed_live_adoption_state, project_managed_mix_adoption_state,
)
from runtime.ui.components.hmi_observer_runtime import _observer_runtime
from runtime.ui.components.hmi_mix_threshold import cv_delta_status, cc_delta_status
from runtime.ui.components.hmi_operator_details import render_operator_details as _render_operator_details, render_operator_details_view
from runtime.ui.components.hmi_service_details import render_operator_service_details as _render_operator_service_details, render_operator_service_details_view
from runtime.ui.components.hmi_compact import _bold_value, _main_mode, _compact_transition, _compact_stage_label, _compact_battery_label, _compact_stage_status, _durable_finish_status
from runtime.ui.components.hmi_live_measurements import _live_measurements
from runtime.ui.components.hmi_auto_stage_progress import auto_stage_progress
from runtime.ui.components.hmi_panel_text import render_operator_panel
from runtime.ui.components.hmi_action_keyboard import (
    _autonomous_keyboard,
    _keyboard_from_actions,
    _managed_adoption_keyboard,
    _managed_mix_keyboard,
    _mix_eligibility_keyboard,
    _ownership_recovery_keyboard,
    _managed_stop_keyboard,
)
from runtime.ui.components.hmi_navigation_keyboards import _back_keyboard, _graph_keyboard, _more_keyboard as _base_more_keyboard
from runtime.ui.components.hmi_compat_dashboard_state import compat_dashboard_state
from runtime.ui.components.hmi_manual_states import _manual_is_interrupted, manual_hmi_state
from runtime.ui.components.hmi_unmanaged_states import unmanaged_hmi_state
from runtime.ui.components.hmi_values import _finite, _on, _regulator, _temperature, _value, _duration
from runtime.ui.components.main_stage_progress import main_stage_countdown_status
from runtime.ui.components.mix_stage_progress import mix_finish_hold_status
from application.operator_views import OperatorDetailsView, ServiceDetailsView
from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from application.operator_button_rules import actions_for_hmi
from application.intents import OperatorIntent, OperatorIntentKind
from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from runtime.ui.telegram.charge import BATTERIES_CALLBACK_DATA, CHARGE_CALLBACK_DATA
from runtime.ui.telegram.details import DETAILS_CALLBACK_DATA
from rd6018_telemetry import RegulationMode, resolve_regulation, telemetry_freshness


_UNKNOWN = {"", "unknown", "unavailable", "none", "null"}


def _build_operator_hmi_state_semantic(app: Any, live: Mapping[str, Any]) -> OperatorHmiState:
    (
        output_on, battery_v, current, power, temp_ext, temp_int, set_v, set_i,
    ) = _live_measurements(live)
    telemetry_stale = not _operator_telemetry_fresh(live)
    regulator = "" if telemetry_stale else _regulator(live)
    safety, attention = _normal_safety(live)

    manager = getattr(app, "rd_control_mode_manager", None)
    hands_off = bool(manager is not None and getattr(manager, "hands_off", False))
    observer, observer_state = _observer_runtime(app)
    observer_visible = observer is not None and observer_state in {"active", "off_pending", "interrupted"}

    if observer_visible:
        fingerprint = getattr(observer, "fingerprint", None)
        if fingerprint is not None:
            set_v = _finite(getattr(fingerprint, "set_voltage_v", set_v))
            set_i = _finite(getattr(fingerprint, "set_current_a", set_i))
        process_state = (
            HmiProcessState.INTERRUPTED if observer_state == "interrupted" else HmiProcessState.ADOPTED_MIX
        )
        return project_managed_live_adoption_state(app, OperatorHmiState(
            process_state=process_state,
            authority=HmiAuthority.ADOPTED_MIX,
            title="RD6018 · MIX ПОДХВАЧЕН" if observer_state != "interrupted" else "RD6018 · MIX ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ",
            output_on=output_on,
            regulator=regulator,
            battery_label=_battery_label_from_observer(observer),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=_observer_progress(observer, observer_state, regulator, hold_seconds=MIX_FINISH_HOLD_S, now_s=time.time()),
            safety=safety,
            attention="warning" if observer_state in {"off_pending", "interrupted"} else attention,
        ))

    controller = getattr(app, "charge_controller", None)
    if controller is not None and bool(getattr(controller, "is_active", False)):
        stage = str(getattr(controller, "current_stage", "") or "")
        stage_label = stage
        label_fn = getattr(app, "_stage_label", None)
        if callable(label_fn):
            try:
                stage_label = str(label_fn(stage, short=True))
            except Exception:
                pass
        battery_type = str(getattr(controller, "battery_type", "") or "")
        capacity = _finite(getattr(controller, "ah_capacity", None))
        battery_label = battery_type
        if capacity is not None and capacity > 0:
            battery_label = f"{battery_label} · {capacity:g} Ah" if battery_label else f"{capacity:g} Ah"
        progress, stage_status, snapshot = auto_stage_progress(
            app, controller, live, stage=stage, regulator=regulator,
            telemetry_stale=telemetry_stale, battery_type=battery_type,
            capacity=capacity, now_s=time.time,
        )
        if telemetry_stale:
            stage_status = "⚠️ Телеметрия устарела · состояние не подтверждено"
            attention = "warning"
        lowered = stage.lower()
        process = HmiProcessState.RUNNING
        if "safe" in lowered or "cool" in lowered or "ожид" in lowered or "осты" in lowered:
            process = HmiProcessState.PAUSED
        elif "storage" in lowered or "хран" in lowered:
            process = HmiProcessState.STORAGE
        pause_state = getattr(app, "_operator_pause_state", None)
        pause_checker = getattr(pause_state, "active", None)
        operator_paused = bool(pause_checker()) if callable(pause_checker) and not hands_off else False
        if operator_paused:
            process = HmiProcessState.PAUSED
        return project_managed_live_adoption_state(app, OperatorHmiState(
            process_state=process,
            authority=HmiAuthority.AUTO,
            title=(
                f"RD6018 · ПАУЗА · {stage_label.upper() if stage_label else 'ЗАРЯД'}"
                if operator_paused
                else f"RD6018 · {stage_label.upper() if stage_label else 'ЗАРЯД'}"
            ),
            output_on=output_on,
            regulator=regulator,
            battery_label=battery_label,
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=progress,
            safety=safety,
            attention=attention,
            stage_status=stage_status,
            finish_evidence=(snapshot.get("finish_evidence") if isinstance(snapshot, Mapping) else None),
        ))

    manual_result = manual_hmi_state(
        app, live,
        output_on=output_on, regulator=regulator, battery_v=battery_v,
        current=current, power=power, temp_ext=temp_ext, temp_int=temp_int,
        set_v=set_v, set_i=set_i, safety=safety, attention=attention,
        now_s=time.time,
    )
    if manual_result is not None:
        return project_managed_live_adoption_state(app, manual_result)
    return project_managed_live_adoption_state(app, unmanaged_hmi_state(
        hands_off=hands_off,
        output_on=output_on, regulator=regulator, battery_v=battery_v,
        current=current, power=power, temp_ext=temp_ext, temp_int=temp_int,
        set_v=set_v, set_i=set_i, safety=safety, attention=attention,
    ))


def build_operator_hmi_state(app: Any, live: Mapping[str, Any]) -> OperatorHmiState:
    """Build this app's HMI projection and attach its current Output evidence."""
    state = _build_operator_hmi_state_semantic(app, live)
    from operator_output_truth import normalize_operator_state

    import operator_hmi as hmi

    state = project_managed_mix_adoption_state(app, state)
    return normalize_operator_state(app, state, live, hmi)


def render_operator_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    from operator_output_truth import _render_unknown_output

    return _render_unknown_output(_render_operator_details(app, state, live), state)


def render_operator_panel_for_app(app: Any, state: OperatorHmiState) -> str:
    """Resolve the composed app's final panel renderer without global patching."""
    renderer = getattr(app, "_render_operator_panel", None)
    return renderer(state) if callable(renderer) else render_operator_panel(state)


def render_operator_service_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    from operator_output_truth import _render_unknown_output

    return _render_unknown_output(_render_operator_service_details(app, state, live), state)


def _more_keyboard(state: OperatorHmiState, app: Any = None) -> InlineKeyboardMarkup:
    markup = _base_more_keyboard(state, app)
    if app is None:
        return markup
    from operator_output_truth import filter_keyboard_for_output_truth, output_known
    import operator_hmi as hmi

    if output_known(state):
        return filter_keyboard_for_output_truth(app, state, markup, hmi)
    from operator_output_truth import _filter_callbacks

    markup = _filter_callbacks(markup, {"rd_hands_off_disable"})
    return filter_keyboard_for_output_truth(app, state, markup, hmi)


# Keep a stable reference to the unwrapped semantic builder. The graph dashboard
# installs a wrapper around this module's public builder at composition time.
_BASE_BUILD_OPERATOR_HMI_STATE = _build_operator_hmi_state_semantic


def _binary(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {"on", "true", "1"}:
        return True
    if raw in {"off", "false", "0"}:
        return False
    return None


def _fresh(live: Mapping[str, Any], *keys: str) -> bool:
    return bool(telemetry_freshness(live, keys).valid)


def _raw_available(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() not in _UNKNOWN


def _regulation_fresh(live: Mapping[str, Any]) -> bool:
    if _raw_available(live.get("regulation_code")):
        return _fresh(live, "regulation_code")
    return _fresh(live, "is_cv", "is_cc")


def _ownership_conflict(app: Any) -> Optional[str]:
    """Return a presentation-level ownership conflict without changing authority."""
    controller = getattr(app, "charge_controller", None)
    auto_active = bool(controller is not None and getattr(controller, "is_active", False))
    manual = getattr(app, "manual_session_manager", None)
    manual_active = bool(manual is not None and getattr(manual, "is_active", False))
    manager = getattr(app, "rd_control_mode_manager", None)
    hands_off = bool(manager is not None and getattr(manager, "hands_off", False))
    observer = getattr(app, "rd_live_mix_observer", None)
    observer_state = ""
    if observer is not None:
        raw_state = getattr(observer, "state", None)
        observer_state = str(getattr(raw_state, "value", raw_state) or "")
    observer_visible = observer is not None and observer_state in {"active", "off_pending", "interrupted"}
    conflicts: list[str] = []
    if auto_active and manual_active:
        conflicts.append("AUTO и MANUAL активны одновременно")
    if observer_visible and (auto_active or manual_active):
        managed = "AUTO" if auto_active and not manual_active else "MANUAL" if manual_active and not auto_active else "AUTO/MANUAL"
        conflicts.append(f"{managed} конфликтует с подхваченным Mix")
    if observer_visible and not hands_off:
        conflicts.append("подхваченный Mix существует вне HANDS_OFF")
    if hands_off and (auto_active or manual_active):
        managed = "AUTO" if auto_active and not manual_active else "MANUAL" if manual_active and not auto_active else "AUTO/MANUAL"
        conflicts.append(f"{managed} активен при HANDS_OFF")
    return "; ".join(conflicts) if conflicts else None


def _contain_idle_for_safety(
    state: OperatorHmiState,
    *, title: str, progress: str, safety: str, attention: str,
) -> OperatorHmiState:
    """Contain an idle panel at presentation level while preserving active state."""
    if state.process_state is not HmiProcessState.IDLE:
        return replace(state, safety=safety, attention=attention)
    return replace(
        state, process_state=HmiProcessState.CONTAINMENT,
        authority=HmiAuthority.CONTAINMENT, title=title, progress=progress,
        safety=safety, attention=attention,
    )


def build_truthful_hmi_state(
    app: Any,
    live: Mapping[str, Any],
    *,
    base_builder=None,
) -> OperatorHmiState:
    """Build truthful semantic HMI state from the existing base state and live read."""
    from operator_output_truth import normalize_operator_state

    import operator_hmi as hmi

    def with_output_truth(state: OperatorHmiState) -> OperatorHmiState:
        return normalize_operator_state(app, state, live, hmi)

    builder = base_builder or _BASE_BUILD_OPERATOR_HMI_STATE
    state = builder(app, live)
    output_state = _binary(live.get("switch"))
    output_fresh = _fresh(live, "switch")
    if output_state is None or not output_fresh:
        reason = "Физическое состояние Output неизвестно" if output_state is None else "Телеметрия Output устарела"
        return with_output_truth(replace(
            state, process_state=HmiProcessState.CONTAINMENT,
            authority=HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT НЕ ПОДТВЕРЖДЁН", output_on=False,
            regulator="—", progress=f"{reason} · новые команды запуска недоступны",
            safety="⚠️ Требуется восстановить достоверную телеметрию RD6018",
            attention="output_unknown",
        ))
    regulation = resolve_regulation(live)
    regulator = ({RegulationMode.CV: "CV", RegulationMode.CC: "CC"}.get(regulation, "—")
                 if _regulation_fresh(live) else "—")
    if regulator != state.regulator:
        state = replace(state, regulator=regulator)
    ownership_conflict = _ownership_conflict(app)
    if ownership_conflict:
        state = replace(
            state, process_state=HmiProcessState.CONTAINMENT,
            authority=HmiAuthority.CONTAINMENT,
            title="RD6018 · КОНФЛИКТ OWNERSHIP", output_on=bool(output_state),
            progress=f"Несогласованная модель управления: {ownership_conflict}",
            safety="⚠️ Управляющие действия скрыты до восстановления единственного owner",
            attention="alarm",
        )
    if _protection_tripped(live):
        return with_output_truth(_contain_idle_for_safety(
            state, title="RD6018 · СРАБОТАЛА ЗАЩИТА",
            progress="Новая программа недоступна до проверки и сброса защитного состояния",
            safety="⚠️ Защита сработала", attention="alarm",
        ))
    return with_output_truth(state)


def build_operator_keyboard(
    app: Any,
    state: OperatorHmiState,
    *,
    actions: OperatorActionsView | None = None,
) -> InlineKeyboardMarkup:
    """Authoritative L2 operator keyboard.

    All callers use the application-owned eligibility rules; this layer renders.
    """
    if actions is not None:
        markup = _keyboard_from_actions(actions)
    else:
        # The shared application rule selector owns eligibility for all callers.
        markup = _managed_adoption_keyboard(app, state, _keyboard_from_actions(actions_for_hmi(state)))
        markup = _mix_eligibility_keyboard(state, markup)
    markup = _managed_mix_keyboard(app, state, markup, actions=actions)
    markup = _ownership_recovery_keyboard(app, state, markup, actions=actions)
    markup = _managed_stop_keyboard(app, state, markup, actions=actions)
    from operator_output_truth import filter_keyboard_for_output_truth

    import operator_hmi as hmi

    return filter_keyboard_for_output_truth(app, state, markup, hmi)


async def _render_graph_workspace(app: Any, call: Any, user_id: int) -> None:
    _chart_mode, graph_since, limit_pts = app._chart_query_params(user_id)
    times, voltages, currents, temps = await app.get_graph_data_with_temp(
        limit=limit_pts,
        since_timestamp=graph_since,
    )
    buf = await asyncio.to_thread(app.generate_chart, times, voltages, currents, temps)
    markup = _graph_keyboard(app, user_id)
    if buf:
        photo = app.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
        await call.message.answer_photo(
            photo,
            caption="<b>График RD6018</b>",
            parse_mode=app.ParseMode.HTML,
            reply_markup=markup,
        )
    else:
        await call.message.answer(
            "<b>График RD6018</b>\n\nНедостаточно данных.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=markup,
        )


def install_operator_hmi(app: Any) -> None:
    """Install the final semantic L2 panel after all ownership/UI wrappers.

    This renderer intentionally supersedes the graph-heavy legacy dashboard. It does
    not change control authority: an externally adopted Mix remains low-level
    HANDS_OFF until a separately validated edge live-adoption contract exists.
    """
    if bool(getattr(app, "_operator_hmi_installed", False)):
        return

    def intent_route_accepted(result: Any) -> bool:
        # Only ACCEPTED authorizes continuation into an existing callback.
        # BLOCKED_BY_SAFETY and REQUIRES_CONFIRMATION must not fall through.
        status = getattr(result, "status", None)
        return str(getattr(status, "value", status)) == "accepted"

    async def route_read_intent(call: Any, kind: OperatorIntentKind) -> bool:
        interface = getattr(app, "operator_interface", None)
        submit = getattr(interface, "submit_intent", None)
        if not callable(submit):
            return True
        user = str(getattr(getattr(call, "from_user", None), "id", "0"))
        result = await submit(OperatorIntent(kind=kind, source="telegram", user=user))
        if not intent_route_accepted(result):
            await call.answer("Действие пока не маршрутизировано", show_alert=True)
            return False
        return True

    async def build_and_send_dashboard(
        chat_id: int,
        user_id: int,
        old_msg_id: Optional[int] = None,
        anchor_msg_id: Optional[int] = None,
    ) -> int:
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            raise RuntimeError("operator interface is not installed")
        snapshot = await interface.get_operator_snapshot()
        actions = await interface.get_operator_actions(snapshot=snapshot)
        from application.operator_snapshot_provider import OperatorSnapshotProvider
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        text = render_operator_panel_for_app(app, state)
        markup = build_operator_keyboard(app, state, actions=actions)
        target = old_msg_id or anchor_msg_id
        if target:
            try:
                await app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=target,
                    text=text,
                    reply_markup=markup,
                    parse_mode=app.ParseMode.HTML,
                )
                app.user_dashboard[user_id] = target
                app.chat_dashboard[chat_id] = target
                return int(target)
            except Exception as exc:
                if "message is not modified" in str(exc).lower():
                    app.user_dashboard[user_id] = target
                    app.chat_dashboard[chat_id] = target
                    return int(target)
                try:
                    await app.bot.delete_message(chat_id, target)
                except Exception:
                    pass
        sent = await app.bot.send_message(
            chat_id,
            text,
            reply_markup=markup,
            parse_mode=app.ParseMode.HTML,
        )
        app.user_dashboard[user_id] = sent.message_id
        app.chat_dashboard[chat_id] = sent.message_id
        return int(sent.message_id)

    app._build_and_send_dashboard = build_and_send_dashboard

    def compact_dashboard_caption(live: Mapping[str, Any], chart_mode: str, mode: str, idle_warning: str) -> str:
        del chart_mode, mode, idle_warning
        return render_operator_panel_for_app(app, build_operator_hmi_state(app, live))

    app._compact_dashboard_caption = compact_dashboard_caption

    def dashboard_keyboard(is_on: bool, user_id: int, *, back_to_dashboard: bool = False) -> InlineKeyboardMarkup:
        if back_to_dashboard:
            return _back_keyboard()
        state = compat_dashboard_state(app, is_on)
        return build_operator_keyboard(app, state)

    app._build_dashboard_keyboard = dashboard_keyboard

    @app.router.callback_query(F.data == "operator_pause_toggle")
    async def _operator_pause_toggle_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        interface = getattr(app, "operator_interface", None)
        submit = getattr(interface, "submit_intent", None)
        if callable(submit):
            user = str(getattr(getattr(call, "from_user", None), "id", "0"))
            kind = (
                OperatorIntentKind.RESUME_CHARGE
                if bool(getattr(app, "_operator_pause_active", lambda: False)())
                else OperatorIntentKind.PAUSE_CHARGE
            )
            result = await submit(OperatorIntent(kind=kind, source="telegram", user=user))
            if not intent_route_accepted(result):
                await call.answer("Пауза пока недоступна", show_alert=True)
                return
        handler = getattr(app, "_operator_pause_toggle", None)
        if handler is None:
            await call.answer("Пауза недоступна", show_alert=True)
            return
        # A managed pause may outlive Telegram's callback-query answer window.
        # A late acknowledgement must not be reported as a failed pause.
        try:
            await call.answer()
        except Exception:
            pass
        try:
            await handler(call)
        except Exception as exc:
            app.logger.exception("operator pause failed: %s", exc)
            return
        # PanelLastMiddleware refreshes the single panel after this callback.
        # A second direct refresh raced the graph and its tracked message ID.

    async def render_graph_for_callback(call: Any, user_id: int, before_render=None) -> None:
        # Use the existing terminal-panel owner for both graph entry and
        # range changes; never publish a competing text/graph panel.
        async def render() -> None:
            if before_render is not None:
                before_render()
            renderer = getattr(app, "_render_graph_workspace", None)
            await (renderer or _render_graph_workspace)(app, call, user_id)

        owner = getattr(app, "terminal_panel_manager", None)
        if owner is not None:
            await owner.render_graph(
                call.message.chat.id, user_id,
                render,
                source_message_id=call.message.message_id,
            )
        else:
            await render()

    @app.router.callback_query(F.data == "operator_graph")
    async def _operator_graph(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_GRAPH):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        await render_graph_for_callback(call, user_id)

    @app.router.callback_query(F.data == "operator_refresh")
    async def _operator_refresh(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.REFRESH_PANEL):
            return
        await call.answer("Обновляю")
        # The single panel lifecycle owner refreshes after this handler.

    @app.router.callback_query(F.data.startswith("operator_graph_"))
    async def _operator_graph_range(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        raw = str(call.data).removeprefix("operator_graph_")
        if raw not in app.CHART_RANGE_VALUES:
            await call.answer("Неизвестный диапазон", show_alert=True)
            return
        user_id = call.from_user.id if call.from_user else 0
        await call.answer()
        await render_graph_for_callback(
            call, user_id, lambda: app.user_chart_range.__setitem__(user_id, raw),
        )

    @app.router.callback_query(F.data == "operator_more")
    async def _operator_more(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_DIAGNOSTICS):
            return
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            await call.answer("Интерфейс чтения недоступен", show_alert=True)
            return
        snapshot = await interface.get_operator_snapshot()
        from application.operator_snapshot_provider import OperatorSnapshotProvider
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        await call.answer()
        await call.message.answer(
            "<b>Ещё</b>\n\nСервисные и диагностические экраны.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=_more_keyboard(state, app),
        )

    @app.router.callback_query(F.data == "operator_adopted_stop")
    async def _operator_adopted_stop(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        observer, state = _observer_runtime(app)
        if observer is None or state not in {"active", "off_pending"}:
            await call.answer("Подхваченная Mix уже не активна", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "<b>Остановить текущий Mix?</b>\n\nБудет выполнен только verified Output OFF. Уставки RD не изменяются.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⏹ ОСТАНОВИТЬ", callback_data="operator_adopted_stop_execute")],
                    [InlineKeyboardButton(text="Продолжить Mix", callback_data="operator_done")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "operator_adopted_stop_execute")
    async def _operator_adopted_stop_execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        manager = getattr(app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "hands_off", False)):
            await call.answer("Verified HANDS_OFF OFF недоступен", show_alert=True)
            return
        await call.answer()
        try:
            await manager.operator_output_off(app.ENTITY_MAP.get("switch"))
            observer = getattr(app, "rd_live_mix_observer", None)
            if observer is not None:
                await observer.observe_once()
        except Exception as exc:
            # The callback was already acknowledged before the potentially
            # slow OFF operation. Telegram permits only one callback ACK;
            # report execution failure in the existing chat instead.
            await call.message.answer(f"Не удалось подтвердить остановку Mix: {exc}")
            return
        await call.message.answer("⏹ Mix остановлен. Output подтверждён OFF.")

    app._operator_hmi_installed = True
