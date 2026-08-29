from __future__ import annotations

import html
import math
from typing import Any, Mapping, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from pb_domain import ChargeIntent
from v2_ui import INTENT_LABELS


_DECISION_LABELS = {
    "finish_stage": "Финиш этапа подтверждён",
    "hold_output_off": "Выход удерживается OFF",
    "rest_and_diagnose": "Пауза и диагностика",
    "pause_thermal": "Термопауза",
}


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _duration(seconds: Any) -> Optional[str]:
    value = _finite(seconds)
    if value is None or value < 0:
        return None
    total = int(value)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours}ч {minutes:02d}м" if hours else f"{minutes}м"


def _intent_text(snapshot: Mapping[str, Any]) -> str:
    raw = snapshot.get("intent")
    if raw in (None, ""):
        return ""
    raw_text = str(raw)
    try:
        return INTENT_LABELS[ChargeIntent(raw_text)]
    except (ValueError, KeyError):
        return raw_text


def _temperature_line(metrics: Mapping[str, Any]) -> Optional[str]:
    trend = _finite(metrics.get("d_temp_c_per_min"))
    if trend is None:
        return None
    if abs(trend) < 0.03:
        return "Температура: стабильно"
    arrow = "↑" if trend > 0 else "↓"
    return f"Температура: {arrow} {trend:+.02f} °C/мин"


def _current_direction(metrics: Mapping[str, Any]) -> str:
    rate = _finite(metrics.get("d_current_a_per_min"))
    if rate is None:
        return "Хвост тока ещё не сформирован"
    if rate < -0.003:
        return "Ток снижается · хвост формируется"
    if rate > 0.003:
        return "Ток растёт · проверяется контекст U/T"
    return "Ток стабилен · формируется полка"


def _voltage_direction(metrics: Mapping[str, Any]) -> str:
    rate = _finite(metrics.get("d_voltage_v_per_min"))
    if rate is None:
        return "Пик напряжения ещё не сформирован"
    if rate > 0.003:
        return "Напряжение растёт · поиск Vmax"
    if rate < -0.003:
        return "Напряжение снижается · проверяется ΔV"
    return "Напряжение стабильно · формируется пик"


def format_active_evidence_pretty(
    snapshot: Mapping[str, Any],
    *,
    voltage_v: Optional[float] = None,
    current_a: Optional[float] = None,
    temp_c: Optional[float] = None,
    include_header: bool = True,
) -> str:
    """Operator-facing evidence block: compact, mode-specific and jargon-light."""

    del voltage_v, current_a, temp_c
    metrics = dict(snapshot.get("metrics") or {})
    lines = []
    intent = _intent_text(snapshot)
    if include_header and intent:
        lines.append(f"<b>{html.escape(intent)}</b>")

    if not snapshot.get("authoritative", True):
        lines.append("⚠️ Управление временно на резервной legacy-логике")

    is_cv = bool(snapshot.get("is_cv"))
    is_cc = bool(snapshot.get("is_cc"))

    if is_cv:
        imin = _finite(metrics.get("current_min_a"))
        age = _duration(metrics.get("seconds_since_current_min"))
        delta = _finite(metrics.get("delta_current_from_min_a"))
        threshold = _finite(metrics.get("reversal_threshold_a"))

        if imin is None or imin <= 0:
            lines.append("<b>CV</b> · Imin: ищем")
            lines.append(_current_direction(metrics))
        else:
            lines.append(f"<b>CV</b> · Imin {imin:.3f} A")
            if delta is not None and threshold is not None:
                age_text = f" · {age}" if age else ""
                lines.append(f"ΔI {delta:+.3f} / {threshold:.3f} A{age_text}")
    elif is_cc:
        vmax = _finite(metrics.get("voltage_max_v"))
        age = _duration(metrics.get("seconds_since_voltage_max"))
        delta = _finite(metrics.get("delta_voltage_from_max_v"))
        threshold = _finite(metrics.get("voltage_reversal_threshold_v"))

        if vmax is None or vmax <= 0:
            lines.append("<b>CC</b> · Vmax: ищем")
            lines.append(_voltage_direction(metrics))
        else:
            lines.append(f"<b>CC</b> · Vmax {vmax:.3f} V")
            if delta is not None and threshold is not None:
                age_text = f" · {age}" if age else ""
                lines.append(f"ΔV {delta:+.3f} / {threshold:.3f} V{age_text}")
    else:
        lines.append("Режим регулятора определяется")

    temp_line = _temperature_line(metrics)
    if temp_line:
        lines.append(temp_line)

    if snapshot.get("finish_hold_started_at") is not None:
        lines.append("Δ подтверждена · <b>финальная выдержка 2 ч</b>")
    else:
        decision = str(snapshot.get("decision") or "continue")
        decision_line = _DECISION_LABELS.get(decision)
        if decision_line:
            lines.append(decision_line)

    return "\n".join(lines)


def build_operator_dashboard_keyboard(
    app: Any,
    is_on: bool,
    user_id: int,
    *,
    back_to_dashboard: bool = False,
) -> InlineKeyboardMarkup:
    """Stable operator hierarchy: one primary action and secondary diagnostics."""

    if back_to_dashboard:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ К панели", callback_data="dash_back")],
            ]
        )

    active = bool(getattr(app.charge_controller, "is_active", False) or is_on)
    chart_mode = app._chart_range_for_user(user_id)

    def chart_button(mode: str, label: str) -> InlineKeyboardButton:
        selected = "● " if chart_mode == mode else ""
        return InlineKeyboardButton(text=f"{selected}{label}", callback_data=f"chart_{mode}")

    rows = [
        [
            InlineKeyboardButton(
                text="🛑 Остановить заряд" if active else "▶ Новая программа",
                callback_data="power_toggle" if active else "charge_modes",
            )
        ],
        [
            InlineKeyboardButton(text="↻ Обновить", callback_data="refresh"),
            InlineKeyboardButton(text="Подробнее", callback_data="info_full"),
        ],
        [
            chart_button(app.CHART_RANGE_30M, "30м"),
            chart_button(app.CHART_RANGE_2H, "2ч"),
            chart_button(app.CHART_RANGE_SESSION, "Сессия"),
        ],
        [
            InlineKeyboardButton(text="АКБ", callback_data="v2_batteries"),
            InlineKeyboardButton(text="События", callback_data="logs"),
        ],
        [
            InlineKeyboardButton(text="Контроллер", callback_data="v2_status"),
            InlineKeyboardButton(text="Диагностика", callback_data="entities_status"),
        ],
    ]
    if not active:
        rows.append(
            [InlineKeyboardButton(text="Условие OFF", callback_data="menu_off")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_dashboard_polish(app: Any, ui_module: Any) -> None:
    """Install the production operator card without changing controller semantics."""

    ui_module.format_active_evidence = format_active_evidence_pretty

    def _compact_dashboard_caption(live, chart_mode: str, mode: str, idle_warning: str) -> str:
        battery_v = _finite(live.get("battery_voltage")) or 0.0
        current = _finite(live.get("current")) or 0.0
        power = _finite(live.get("power")) or 0.0
        ah = _finite(live.get("ah")) or 0.0
        temp_ext = _finite(live.get("temp_ext"))
        temp_int = _finite(live.get("temp_int"))
        set_v = _finite(live.get("set_voltage"))
        set_i = _finite(live.get("set_current"))
        is_on = str(live.get("switch", "")).lower() == "on"
        ovp_tr = str(live.get("ovp_triggered", "")).lower() == "on"
        ocp_tr = str(live.get("ocp_triggered", "")).lower() == "on"

        controller = app.charge_controller
        lines = []
        snapshot: Mapping[str, Any] = {}

        if controller.is_active:
            try:
                snapshot = controller.v2_ui_snapshot()
            except Exception:
                snapshot = {}
            profile = html.escape(str(controller.battery_type))
            capacity = int(getattr(controller, "ah_capacity", 0) or 0)
            capacity_text = f" {capacity} Ah" if capacity > 0 else ""
            intent = _intent_text(snapshot)
            intent_text = f" · {html.escape(intent)}" if intent else ""
            lines.append(f"<b>RD6018 · {profile}{capacity_text}{intent_text}</b>")

            try:
                timers = controller.get_timers()
                total_time = html.escape(str(timers.get("total_time", "—")))
            except Exception:
                total_time = "—"
            stage = html.escape(app._stage_label(controller.current_stage, short=True))
            output_text = "ON" if is_on else "OFF"
            lines.append(f"<b>{stage}</b> · {html.escape(mode)} · {total_time} · Output {output_text}")
        else:
            title = "Ручное управление" if is_on else "Готов"
            lines.append(f"<b>RD6018 · {title}</b>")
            lines.append(f"Output {'ON' if is_on else 'OFF'} · {html.escape(mode)}")

        lines.append(f"<b>{battery_v:.2f} V</b>   <b>{current:.2f} A</b>   {power:.1f} W")
        temp_ext_text = f"{temp_ext:.1f}°C" if temp_ext is not None else "—"
        temp_int_text = f"{temp_int:.1f}°C" if temp_int is not None else "—"
        lines.append(f"АКБ {temp_ext_text} · БП {temp_int_text} · +{ah:.2f} Ah")
        if set_v is not None and set_i is not None:
            lines.append(f"Уставки {set_v:.2f} V / {set_i:.2f} A")

        if controller.is_active and controller.current_stage in {
            controller.STAGE_MAIN,
            controller.STAGE_MIX,
        }:
            try:
                evidence = format_active_evidence_pretty(snapshot, include_header=False)
            except Exception:
                evidence = ""
            if evidence:
                lines.append(evidence)
        elif controller.is_active:
            try:
                progress = app._format_stage_progress_line(live)
            except Exception:
                progress = ""
            if progress:
                lines.append(progress)

        alerts = []
        if ovp_tr or ocp_tr:
            active_protections = "/".join(
                name for name, state in (("OVP", ovp_tr), ("OCP", ocp_tr)) if state
            )
            alerts.append(f"⚠️ {active_protections} сработала")
        if idle_warning:
            alerts.append("⚠️ Выход включён вне программы")
        try:
            if app._format_manual_off_for_dashboard():
                alerts.append("Условие OFF активно")
        except Exception:
            pass
        if temp_ext is not None and temp_ext >= 35.0:
            alerts.append(f"АКБ {temp_ext:.1f}°C")
        if temp_int is not None and temp_int >= 50.0:
            alerts.append(f"БП {temp_int:.1f}°C")

        safety = " · ".join(alerts) if alerts else "Защита: норма"
        lines.append(f"{safety} · График {html.escape(app._chart_label(chart_mode))}")
        return "\n".join(line for line in lines if line)

    app._compact_dashboard_caption = _compact_dashboard_caption
