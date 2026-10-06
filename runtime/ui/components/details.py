"""Framework-neutral formatter for operator details."""

from __future__ import annotations

import html
from typing import Optional

from application.operator_views import OperatorDetailsView


def _temperature(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}°C"


def _value(value: Optional[float], digits: int, suffix: str) -> str:
    return "—" if value is None else f"{value:.{digits}f} {suffix}"


def render_operator_details_body(view: OperatorDetailsView) -> str:
    lines: list[str] = []
    if view.observer_state in {"active", "off_pending", "interrupted"}:
        lines.extend(
            [
                f"Сессия: <b>{'Mix подхвачен' if view.observer_state != 'interrupted' else 'подхват прерван'}</b>",
                f"АКБ: {html.escape(view.battery_label or '—')}",
                f"Output: {'ON' if view.output_on else 'OFF'} · {html.escape(view.regulator)}",
                f"Уставки прибора: {_value(view.target_voltage_v, 2, 'V')} / {_value(view.current_limit_a, 2, 'A')}",
                f"Состояние наблюдателя: <code>{html.escape(view.observer_state or '—')}</code>",
            ]
        )
        if view.observer_status:
            lines.append(f"\nПоследнее: <code>{html.escape(view.observer_status)}</code>")
    else:
        lines.extend(
            [
                f"Состояние: <b>{html.escape(view.process_state)}</b> · Authority: <code>{html.escape(view.authority)}</code>",
                f"Output: <b>{'ON' if view.output_on else 'OFF'}</b> · режим {html.escape(view.regulator)}",
                f"⚡ {_value(view.battery_voltage_v, 3, 'V')} · {_value(view.current_a, 3, 'A')}",
                f"🌡 АКБ: {_temperature(view.battery_temp_c)} · БП: {_temperature(view.psu_temp_c)}",
            ]
        )
        if view.stage or view.battery_type:
            lines.extend(
                [
                    "",
                    "🧠 <b>Статистика по этапу</b>",
                    f"📍 Этап: <b>{html.escape(view.stage or '—')}</b>",
                    f"🔋 АКБ: {html.escape(view.battery_type or view.battery_label or '—')}"
                    + (f" · {view.capacity_ah:g} Ah" if view.capacity_ah else ""),
                    f"⏱ Этап: {html.escape(view.stage_time)} · всего {html.escape(view.total_time)}",
                    f"⌛ Лимит: {html.escape(view.remaining_time)}",
                    f"📦 Набрано: {_value(view.delivered_ah, 2, 'Ah')}",
                ]
            )
        elif view.manual_capacity_ah is not None:
            lines.extend(
                [
                    "",
                    "🧠 <b>Статистика ручного заряда</b>",
                    f"🔋 Заданная ёмкость: {_value(view.manual_capacity_ah, 2, 'Ah')}",
                ]
            )
        lines.extend(
            [
                f"🎯 Уставки: {_value(view.target_voltage_v, 2, 'V')} · лимит {_value(view.current_limit_a, 2, 'A')}",
                f"🔌 Вход: {_value(view.input_voltage_v, 1, 'V')} · ⏱ Работа: {html.escape(view.uptime)}",
            ]
        )
    lines.append(f"🛡 Защита: {html.escape(view.safety)}")
    return "\n".join(lines)


__all__ = ["render_operator_details_body"]
