from __future__ import annotations

import asyncio
import html
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class HmiProcessState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STORAGE = "storage"
    CONTAINMENT = "containment"
    HANDS_OFF = "hands_off"
    ADOPTED_MIX = "adopted_mix"
    INTERRUPTED = "interrupted"


class HmiAuthority(str, Enum):
    NONE = "none"
    AUTO = "auto"
    MANUAL = "manual"
    EXTERNAL = "external"
    ADOPTED_MIX = "adopted_mix"
    CONTAINMENT = "containment"


@dataclass(frozen=True)
class OperatorHmiState:
    process_state: HmiProcessState
    authority: HmiAuthority
    title: str
    output_on: bool
    regulator: str
    battery_label: str
    battery_voltage_v: Optional[float]
    current_a: Optional[float]
    power_w: Optional[float]
    battery_temp_c: Optional[float]
    psu_temp_c: Optional[float]
    target_voltage_v: Optional[float]
    current_limit_a: Optional[float]
    progress: str
    safety: str
    attention: str = "normal"


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"on", "true", "1"}


def _regulator(live: Mapping[str, Any]) -> str:
    if _on(live.get("is_cv")):
        return "CV"
    if _on(live.get("is_cc")):
        return "CC"
    return "—"


def _temperature(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}°C"


def _value(value: Optional[float], digits: int, suffix: str) -> str:
    return "—" if value is None else f"{value:.{digits}f} {suffix}"


def _observer_runtime(app: Any) -> tuple[Any, str]:
    observer = getattr(app, "rd_live_mix_observer", None)
    if observer is None:
        return None, ""
    state = str(getattr(getattr(observer, "state", None), "value", getattr(observer, "state", "")) or "")
    return observer, state


def _observer_progress(observer: Any, state: str, regulator: str) -> str:
    if state == "off_pending":
        return "Финиш подтверждён · Output OFF ожидает подтверждения"
    if state == "interrupted":
        return "Подхват прерван перезапуском · требуется новое подтверждение"
    hold_started = getattr(observer, "finish_hold_started_at_s", None)
    if hold_started is not None:
        held_s = max(0.0, time.time() - float(hold_started))
        held_m = int(held_s // 60)
        return f"Δ подтверждена · выдержка {held_m // 60}ч {held_m % 60:02d}м / 2ч"
    if regulator == "CV":
        return "Финиш: свежий Imin → ΔI · затем 2ч → OFF"
    if regulator == "CC":
        return "Финиш: свежий Vmax → ΔV · затем 2ч → OFF"
    return "Финишный критерий начнёт считаться после подтверждения режима CV/CC"


def _battery_label_from_observer(observer: Any) -> str:
    battery_id = str(getattr(observer, "battery_id", "") or "").strip()
    chemistry = getattr(observer, "chemistry", None)
    chemistry_text = str(getattr(chemistry, "value", chemistry) or "").strip()
    capacity = _finite(getattr(observer, "capacity_ah", None))
    pieces = [piece for piece in (battery_id, chemistry_text) if piece]
    if capacity is not None and capacity > 0:
        pieces.append(f"{capacity:g} Ah")
    return " · ".join(pieces)


def _normal_safety(live: Mapping[str, Any]) -> tuple[str, str]:
    tripped = []
    if _on(live.get("ovp_triggered")):
        tripped.append("OVP")
    if _on(live.get("ocp_triggered")):
        tripped.append("OCP")
    if tripped:
        return "⚠️ Защита: " + "/".join(tripped), "alarm"
    return "Защита: норма", "normal"


def build_operator_hmi_state(app: Any, live: Mapping[str, Any]) -> OperatorHmiState:
    output_on = _on(live.get("switch"))
    regulator = _regulator(live)
    battery_v = _finite(live.get("battery_voltage"))
    current = _finite(live.get("current"))
    power = _finite(live.get("power"))
    temp_ext = _finite(live.get("temp_ext_v2"))
    if temp_ext is None:
        temp_ext = _finite(live.get("temp_ext"))
    temp_int = _finite(live.get("temp_int_v2"))
    if temp_int is None:
        temp_int = _finite(live.get("temp_int"))
    set_v = _finite(live.get("set_voltage"))
    set_i = _finite(live.get("set_current"))
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
            progress=_observer_progress(observer, observer_state, regulator),
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
        progress = ""
        progress_fn = getattr(app, "_format_stage_progress_line", None)
        if callable(progress_fn):
            try:
                progress = str(progress_fn(dict(live)) or "")
            except Exception:
                progress = ""
        lowered = stage.lower()
        process = HmiProcessState.RUNNING
        if "safe" in lowered or "cool" in lowered or "ожид" in lowered or "осты" in lowered:
            process = HmiProcessState.PAUSED
        elif "storage" in lowered or "хран" in lowered:
            process = HmiProcessState.STORAGE
        return OperatorHmiState(
            process_state=process,
            authority=HmiAuthority.AUTO,
            title=f"RD6018 · {stage_label.upper() if stage_label else 'ЗАРЯД'}",
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
        )

    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and bool(getattr(manual, "is_active", False)):
        return OperatorHmiState(
            process_state=HmiProcessState.RUNNING,
            authority=HmiAuthority.MANUAL,
            title="RD6018 · РУЧНОЙ РЕЖИМ",
            output_on=output_on,
            regulator=regulator,
            battery_label=str(getattr(manual, "battery_id", "") or ""),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress="Управляемая ручная сессия",
            safety=safety,
            attention=attention,
        )

    if hands_off:
        return OperatorHmiState(
            process_state=HmiProcessState.HANDS_OFF,
            authority=HmiAuthority.EXTERNAL,
            title="RD6018 · РУЧНОЕ УПРАВЛЕНИЕ",
            output_on=output_on,
            regulator=regulator,
            battery_label="",
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=(
                "Внешняя сессия · автоматика не меняет Output и уставки"
                if output_on
                else "RD свободен от Pb-автоматики"
            ),
            safety=safety,
            attention=attention,
        )

    if output_on:
        return OperatorHmiState(
            process_state=HmiProcessState.CONTAINMENT,
            authority=HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT ВНЕ СЕССИИ",
            output_on=True,
            regulator=regulator,
            battery_label="",
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress="Нет подтверждённой управляемой сессии",
            safety="⚠️ Требуется проверка ownership",
            attention="alarm",
        )

    return OperatorHmiState(
        process_state=HmiProcessState.IDLE,
        authority=HmiAuthority.NONE,
        title="RD6018 · ГОТОВ",
        output_on=False,
        regulator=regulator,
        battery_label="",
        battery_voltage_v=battery_v,
        current_a=current,
        power_w=power,
        battery_temp_c=temp_ext,
        psu_temp_c=temp_int,
        target_voltage_v=set_v,
        current_limit_a=set_i,
        progress="Готов к новой программе",
        safety=safety,
        attention=attention,
    )


def render_operator_panel(state: OperatorHmiState) -> str:
    lines = [f"<b>{html.escape(state.title)}</b>", ""]
    if state.battery_label:
        lines.append(f"🔋 {html.escape(state.battery_label)}")
    output = "ON" if state.output_on else "OFF"
    regulator = f" · {state.regulator}" if state.regulator != "—" else ""
    lines.append(f"Output <b>{output}</b>{regulator}")
    lines.append("")
    electrical = [
        f"<b>{_value(state.battery_voltage_v, 2, 'V')}</b>",
        f"<b>{_value(state.current_a, 2, 'A')}</b>",
    ]
    if state.power_w is not None:
        electrical.append(_value(state.power_w, 1, "W"))
    lines.append("   ".join(electrical))
    lines.append(f"АКБ {_temperature(state.battery_temp_c)} · БП {_temperature(state.psu_temp_c)}")
    if state.target_voltage_v is not None or state.current_limit_a is not None:
        target = _value(state.target_voltage_v, 2, "V")
        limit = _value(state.current_limit_a, 2, "A")
        lines.append(f"Цель {target} · лимит {limit}")
    if state.progress:
        lines.extend(["", html.escape(state.progress)])
    lines.extend(["", html.escape(state.safety)])
    return "\n".join(lines)


def build_operator_keyboard(app: Any, state: OperatorHmiState) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if state.process_state is HmiProcessState.ADOPTED_MIX:
        rows.append([InlineKeyboardButton(text="⏹ Остановить Mix", callback_data="operator_adopted_stop")])
        rows.append(
            [
                InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details"),
                InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="🔋 АКБ", callback_data="v2_batteries"),
                InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more"),
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    if state.process_state is HmiProcessState.INTERRUPTED:
        rows.append([InlineKeyboardButton(text="🧲 Подхватить заново", callback_data="rd_live_mix")])
        rows.append(
            [
                InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details"),
                InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
            ]
        )
        rows.append([InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    if state.process_state is HmiProcessState.HANDS_OFF:
        if state.output_on:
            rows.append([InlineKeyboardButton(text="🧲 Подхватить текущий Mix", callback_data="rd_live_mix")])
            rows.append([InlineKeyboardButton(text="⏹ Output OFF", callback_data="rd_hands_off_output_off")])
        rows.append(
            [
                InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details"),
                InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
            ]
        )
        rows.append([InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    if state.process_state is HmiProcessState.IDLE:
        rows.append([InlineKeyboardButton(text="▶ Новая программа", callback_data="charge_modes")])
        rows.append(
            [
                InlineKeyboardButton(text="🛠 Ручной режим", callback_data="v2_manual_choose"),
                InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="🔋 АКБ", callback_data="v2_batteries"),
                InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more"),
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    if state.authority in {HmiAuthority.AUTO, HmiAuthority.MANUAL}:
        rows.append([InlineKeyboardButton(text="🛑 Остановить заряд", callback_data="power_toggle")])
        rows.append(
            [
                InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details"),
                InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
            ]
        )
        rows.append([InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    rows.append(
        [
            InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details"),
            InlineKeyboardButton(text="📈 График", callback_data="operator_graph"),
        ]
    )
    rows.append([InlineKeyboardButton(text="⋯ Ещё", callback_data="operator_more")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_operator_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    lines = ["<b>Подробности RD6018</b>", ""]
    if state.process_state in {HmiProcessState.ADOPTED_MIX, HmiProcessState.INTERRUPTED}:
        observer, observer_state = _observer_runtime(app)
        lines.extend(
            [
                f"Сессия: <b>{'Mix подхвачен' if observer_state != 'interrupted' else 'подхват прерван'}</b>",
                f"АКБ: {html.escape(state.battery_label or '—')}",
                f"Output: {'ON' if state.output_on else 'OFF'} · {html.escape(state.regulator)}",
                f"Уставки прибора: {_value(state.target_voltage_v, 2, 'V')} / {_value(state.current_limit_a, 2, 'A')}",
                f"Состояние наблюдателя: <code>{html.escape(observer_state or '—')}</code>",
                "",
                "Бот не переписывал текущие V/I/OVP/OCP при подхвате. История HA — только контекст; "
                "финишное Delta-доказательство считается заново после подтверждения.",
                "",
                "Низкоуровневая граница RD остаётся HANDS_OFF: текущий deployed ESPHome ещё не имеет "
                "валидированного live-adopt handshake для PB_MANAGED. Для этой сессии бот владеет только "
                "Delta-наблюдением и, если выбран соответствующий режим, verified Output OFF.",
            ]
        )
        if observer is not None:
            status = str(getattr(observer, "last_status", "") or "")
            if status:
                lines.append(f"\nПоследнее: <code>{html.escape(status)}</code>")
    else:
        lines.extend(
            [
                f"Состояние: <b>{html.escape(state.process_state.value)}</b>",
                f"Authority: <code>{html.escape(state.authority.value)}</code>",
                f"Output: {'ON' if state.output_on else 'OFF'} · {html.escape(state.regulator)}",
                f"Vbat: {_value(state.battery_voltage_v, 3, 'V')}",
                f"Iout: {_value(state.current_a, 3, 'A')}",
                f"T АКБ: {_temperature(state.battery_temp_c)}",
                f"T БП: {_temperature(state.psu_temp_c)}",
            ]
        )
    ovp = _finite(live.get("ovp"))
    ocp = _finite(live.get("ocp"))
    lines.append(f"\nЗащиты RD: OVP {_value(ovp, 2, 'V')} · OCP {_value(ocp, 2, 'A')}")
    return "\n".join(lines)


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")]]
    )


def _graph_keyboard(app: Any, user_id: int) -> InlineKeyboardMarkup:
    selected = str(app._chart_range_for_user(user_id))

    def button(mode: str, text: str) -> InlineKeyboardButton:
        marker = "● " if selected == mode else ""
        return InlineKeyboardButton(text=f"{marker}{text}", callback_data=f"operator_graph_{mode}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(app.CHART_RANGE_30M, "30м"),
                button(app.CHART_RANGE_2H, "2ч"),
                button(app.CHART_RANGE_SESSION, "Сессия"),
            ],
            [InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")],
        ]
    )


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


def _more_keyboard(state: OperatorHmiState) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📋 События", callback_data="logs"),
            InlineKeyboardButton(text="🎛 Контроллер", callback_data="v2_status"),
        ],
        [
            InlineKeyboardButton(text="🩺 Диагностика", callback_data="entities_status"),
            InlineKeyboardButton(text="🧠 AI анализ", callback_data="ai_analysis"),
        ],
    ]
    if state.process_state is HmiProcessState.ADOPTED_MIX:
        rows.append([InlineKeyboardButton(text="🧲 Статус Mix", callback_data="rd_live_mix_status")])
    if state.process_state is HmiProcessState.HANDS_OFF and not state.output_on:
        rows.append([InlineKeyboardButton(text="🔒 Вернуть Pb-контроль", callback_data="rd_hands_off_disable")])
    rows.append([InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_operator_hmi(app: Any) -> None:
    """Install the final semantic L2 panel after all ownership/UI wrappers.

    This renderer intentionally supersedes the graph-heavy legacy dashboard. It does
    not change control authority: an externally adopted Mix remains low-level
    HANDS_OFF until a separately validated edge live-adoption contract exists.
    """
    if bool(getattr(app, "_operator_hmi_installed", False)):
        return

    async def build_and_send_dashboard(
        chat_id: int,
        user_id: int,
        old_msg_id: Optional[int] = None,
        anchor_msg_id: Optional[int] = None,
    ) -> int:
        live = await app.hass.get_all_live()
        state = build_operator_hmi_state(app, live)
        text = render_operator_panel(state)
        markup = build_operator_keyboard(app, state)
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
        # Keyboard rendering itself has no live dict. Build a conservative state from
        # the known ownership/session facts; normal dashboard rendering uses full live.
        observer, observer_state = _observer_runtime(app)
        manager = getattr(app, "rd_control_mode_manager", None)
        if observer is not None and observer_state in {"active", "off_pending", "interrupted"}:
            state = OperatorHmiState(
                HmiProcessState.INTERRUPTED if observer_state == "interrupted" else HmiProcessState.ADOPTED_MIX,
                HmiAuthority.ADOPTED_MIX,
                "",
                bool(is_on),
                "—",
                _battery_label_from_observer(observer),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "",
                "",
            )
        elif manager is not None and bool(getattr(manager, "hands_off", False)):
            state = OperatorHmiState(HmiProcessState.HANDS_OFF, HmiAuthority.EXTERNAL, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        elif bool(getattr(app.charge_controller, "is_active", False)):
            state = OperatorHmiState(HmiProcessState.RUNNING, HmiAuthority.AUTO, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        elif getattr(app, "manual_session_manager", None) is not None and bool(getattr(app.manual_session_manager, "is_active", False)):
            state = OperatorHmiState(HmiProcessState.RUNNING, HmiAuthority.MANUAL, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        else:
            state = OperatorHmiState(HmiProcessState.IDLE if not is_on else HmiProcessState.CONTAINMENT, HmiAuthority.NONE if not is_on else HmiAuthority.CONTAINMENT, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        return build_operator_keyboard(app, state)

    app._build_dashboard_keyboard = dashboard_keyboard

    @app.router.callback_query(F.data == "operator_details")
    async def _operator_details(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        live = await app.hass.get_all_live()
        state = build_operator_hmi_state(app, live)
        await call.answer()
        await call.message.answer(
            render_operator_details(app, state, live),
            parse_mode=app.ParseMode.HTML,
            reply_markup=_back_keyboard(),
        )

    @app.router.callback_query(F.data == "operator_graph")
    async def _operator_graph(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        await _render_graph_workspace(app, call, user_id)

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
        await _render_graph_workspace(app, call, user_id)

    @app.router.callback_query(F.data == "operator_more")
    async def _operator_more(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        live = await app.hass.get_all_live()
        state = build_operator_hmi_state(app, live)
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

    @app.router.callback_query(F.data == "operator_done")
    async def _operator_done(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()

    app._operator_hmi_installed = True
