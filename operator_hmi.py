from __future__ import annotations

import asyncio
import html
import math
import re
import time
from typing import Any, Mapping, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from manual_mode import MANUAL_MIX_FINISH_HOLD_SEC
from rd_live_adoption import MIX_FINISH_HOLD_S
from runtime.ui.labels.operator_actions import OPERATOR_ACTION_LABELS
from runtime.ui.components.manual_extrema_progress import _manual_extrema_status
from runtime.ui.components.adopted_mix_progress import _observer_progress
from runtime.ui.components.hmi_battery_identity import _battery_label_from_manual, _battery_label_from_observer
from runtime.ui.components.hmi_live_safety import _normal_safety, _operator_telemetry_fresh
from runtime.ui.hmi_layout_config import PANEL_HEADING_TARGET_WIDTH, PANEL_HEADING_MIN_GAP
from runtime.ui.components.hmi_state import HmiProcessState, HmiAuthority, OperatorHmiState
from runtime.ui.components.hmi_observer_runtime import _observer_runtime
from runtime.ui.components.hmi_mix_threshold import cv_delta_status, cc_delta_status
from runtime.ui.components.hmi_operator_details import render_operator_details, render_operator_details_view
from runtime.ui.components.hmi_service_details import render_operator_service_details, render_operator_service_details_view
from runtime.ui.components.hmi_compact import _bold_value, _main_mode, _compact_transition, _compact_stage_label, _compact_battery_label, _compact_stage_status, _durable_finish_status
from runtime.ui.components.hmi_live_measurements import _live_measurements
from runtime.ui.components.hmi_auto_stage_progress import auto_stage_progress
from runtime.ui.components.hmi_panel_text import render_operator_panel
from runtime.ui.components.hmi_action_keyboard import _keyboard_from_actions
from runtime.ui.components.hmi_navigation_keyboards import _back_keyboard, _graph_keyboard, _more_keyboard
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


def build_operator_hmi_state(app: Any, live: Mapping[str, Any]) -> OperatorHmiState:
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
        return OperatorHmiState(
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
        )

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
        operator_paused = bool(getattr(app, "_operator_pause_active", lambda: False)())
        if operator_paused:
            process = HmiProcessState.PAUSED
        return OperatorHmiState(
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
        )

    manual_result = manual_hmi_state(
        app, live,
        output_on=output_on, regulator=regulator, battery_v=battery_v,
        current=current, power=power, temp_ext=temp_ext, temp_int=temp_int,
        set_v=set_v, set_i=set_i, safety=safety, attention=attention,
        now_s=time.time,
    )
    if manual_result is not None:
        return manual_result
    return unmanaged_hmi_state(
        hands_off=hands_off,
        output_on=output_on, regulator=regulator, battery_v=battery_v,
        current=current, power=power, temp_ext=temp_ext, temp_int=temp_int,
        set_v=set_v, set_i=set_i, safety=safety, attention=attention,
    )


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
        return _keyboard_from_actions(actions)

    # The shared application rule selector owns eligibility for all callers.
    return _keyboard_from_actions(actions_for_hmi(state))


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

    async def route_read_intent(call: Any, kind: OperatorIntentKind) -> bool:
        interface = getattr(app, "operator_interface", None)
        submit = getattr(interface, "submit_intent", None)
        if not callable(submit):
            return True
        user = str(getattr(getattr(call, "from_user", None), "id", "0"))
        result = await submit(OperatorIntent(kind=kind, source="telegram", user=user))
        if getattr(result, "status", None) == "rejected":
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
        text = render_operator_panel(state)
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
        return render_operator_panel(build_operator_hmi_state(app, live))

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
            if getattr(result, "status", None) == "rejected":
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

    @app.router.callback_query(F.data == "operator_graph")
    async def _operator_graph(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_GRAPH):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        owner = getattr(app, "terminal_panel_manager", None)
        if owner is not None:
            await owner.render_graph(
                call.message.chat.id, user_id,
                lambda: _render_graph_workspace(app, call, user_id),
            )
        else:
            await _render_graph_workspace(app, call, user_id)

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
        app.user_chart_range[user_id] = raw
        await call.answer()
        owner = getattr(app, "terminal_panel_manager", None)
        if owner is not None:
            await owner.render_graph(
                call.message.chat.id, user_id,
                lambda: _render_graph_workspace(app, call, user_id),
            )
        else:
            await _render_graph_workspace(app, call, user_id)

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
            reply_markup=_more_keyboard(state),
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
            await call.answer(str(exc), show_alert=True)
            return
        await call.message.answer("⏹ Mix остановлен. Output подтверждён OFF.")

    app._operator_hmi_installed = True
