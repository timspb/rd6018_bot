"""Read-only operator details (live and immutable DTO presentations)."""
from __future__ import annotations
import html
import re
from typing import Any, Mapping
from application.operator_views import OperatorDetailsView
from .hmi_state import OperatorHmiState, HmiProcessState
from .hmi_values import _finite, _value, _temperature, _duration
from .hmi_observer_runtime import _observer_runtime


def render_operator_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    lines = ["<b>📋 Информация для оператора</b>", ""]
    ah = _finite(live.get("ah"))
    uptime = str(live.get("uptime") or "—")
    input_voltage = _finite(live.get("input_voltage"))
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
                f"Состояние: <b>{html.escape(state.process_state.value)}</b> · "
                f"Authority: <code>{html.escape(state.authority.value)}</code>",
                f"Output: <b>{'ON' if state.output_on else 'OFF'}</b> · режим {html.escape(state.regulator)}",
                f"⚡ {_value(state.battery_voltage_v, 3, 'V')} · {_value(state.current_a, 3, 'A')}",
                f"🌡 АКБ: {_temperature(state.battery_temp_c)} · БП: {_temperature(state.psu_temp_c)}",
            ]
        )
        controller = getattr(app, "charge_controller", None)
        if controller is not None and bool(getattr(controller, "is_active", False)):
            try:
                timers = controller.get_timers()
            except Exception:
                timers = {}
            stage = str(getattr(controller, "current_stage", "") or "—")
            battery_type = str(getattr(controller, "battery_type", "") or "—")
            capacity = _finite(getattr(controller, "ah_capacity", None))
            lines.extend(
                [
                    "",
                    "🧠 <b>Статистика по этапу</b>",
                    f"📍 Этап: <b>{html.escape(stage)}</b>",
                    f"🔋 АКБ: {html.escape(battery_type)} · {capacity:g} Ah" if capacity else f"🔋 АКБ: {html.escape(battery_type)}",
                    f"⏱ Этап: {html.escape(str(timers.get('stage_time', '—')))} · всего {html.escape(str(timers.get('total_time', '—')))}",
                    f"⌛ Лимит: {html.escape(str(timers.get('remaining_time', '—')))}",
                    f"📦 Набрано: {_value(ah, 2, 'Ah')}",
                ]
            )
            if state.progress:
                progress = html.unescape(re.sub(r"<[^>]*>", "", " ".join(str(state.progress).split())))
                lines.append(f"🎯 Финиш: {html.escape(progress)}")
        else:
            manual = getattr(app, "manual_session_manager", None)
            if manual is not None and bool(getattr(manual, "is_active", False)):
                request = getattr(manual, "request", None)
                elapsed = _duration(getattr(manual, "active_elapsed_s", None))
                limit = getattr(getattr(request, "stop", None), "max_active_seconds", None)
                remaining = "—"
                if _finite(limit) is not None and _finite(getattr(manual, "active_elapsed_s", None)) is not None:
                    remaining = _duration(max(0.0, float(limit) - float(manual.active_elapsed_s)))
                capacity = _finite(getattr(request, "capacity_ah", None)) if request is not None else None
                lines.extend(
                    [
                        "",
                        "🧠 <b>Статистика ручного заряда</b>",
                        f"📍 Этап: <b>Ручной режим</b>",
                        f"⏱ Этап: {elapsed} · всего {elapsed}",
                        f"⌛ Лимит: {remaining}",
                        f"📦 Отдано: {_value(ah, 2, 'Ah')}",
                        f"🔋 Заданная ёмкость: {_value(capacity, 2, 'Ah')}",
                    ]
                )
        lines.extend(
            [
                f"🎯 Уставки: {_value(state.target_voltage_v, 2, 'V')} · лимит {_value(state.current_limit_a, 2, 'A')}",
                f"🔌 Вход: {_value(input_voltage, 1, 'V')} · ⏱ Работа: {html.escape(uptime)}",
            ]
        )
    lines.append(f"🛡 Защита: {html.escape(state.safety)}")
    return "\n".join(lines)


def render_operator_details_view(view: OperatorDetailsView) -> str:
    """Render a read-only DTO without accessing runtime objects."""
    lines = ["<b>📋 Информация для оператора</b>", ""]
    if view.observer_state in {"active", "off_pending", "interrupted"}:
        lines.extend([
            f"Сессия: <b>{'Mix подхвачен' if view.observer_state != 'interrupted' else 'подхват прерван'}</b>",
            f"АКБ: {html.escape(view.battery_label or '—')}",
            f"Output: {'ON' if view.output_on else 'OFF'} · {html.escape(view.regulator)}",
            f"Уставки прибора: {_value(view.target_voltage_v, 2, 'V')} / {_value(view.current_limit_a, 2, 'A')}",
            f"Состояние наблюдателя: <code>{html.escape(view.observer_state or '—')}</code>",
        ])
        if view.observer_status:
            lines.append(f"\nПоследнее: <code>{html.escape(view.observer_status)}</code>")
    else:
        lines.extend([
            f"Состояние: <b>{html.escape(view.process_state)}</b> · Authority: <code>{html.escape(view.authority)}</code>",
            f"Output: <b>{'ON' if view.output_on else 'OFF'}</b> · режим {html.escape(view.regulator)}",
            f"⚡ {_value(view.battery_voltage_v, 3, 'V')} · {_value(view.current_a, 3, 'A')}",
            f"🌡 АКБ: {_temperature(view.battery_temp_c)} · БП: {_temperature(view.psu_temp_c)}",
        ])
        if view.stage or view.battery_type:
            lines.extend([
                "", "🧠 <b>Статистика по этапу</b>",
                f"📍 Этап: <b>{html.escape(view.stage or '—')}</b>",
                f"🔋 АКБ: {html.escape(view.battery_type or view.battery_label or '—')}" + (f" · {view.capacity_ah:g} Ah" if view.capacity_ah else ""),
                f"⏱ Этап: {html.escape(view.stage_time)} · всего {html.escape(view.total_time)}",
                f"⌛ Лимит: {html.escape(view.remaining_time)}",
                f"📦 Набрано: {_value(view.delivered_ah, 2, 'Ah')}",
            ])
        elif view.manual_capacity_ah is not None:
            lines.extend(["", "🧠 <b>Статистика ручного заряда</b>", f"🔋 Заданная ёмкость: {_value(view.manual_capacity_ah, 2, 'Ah')}"])
        lines.extend([
            f"🎯 Уставки: {_value(view.target_voltage_v, 2, 'V')} · лимит {_value(view.current_limit_a, 2, 'A')}",
            f"🔌 Вход: {_value(view.input_voltage_v, 1, 'V')} · ⏱ Работа: {html.escape(view.uptime)}",
        ])
    lines.append(f"🛡 Защита: {html.escape(view.safety)}")
    return "\n".join(lines)
