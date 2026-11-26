"""Optional AI-only context, prompt payload and trend preparation."""
from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any, Callable, Mapping

from application.operator_read_source import OperatorReadSource

_AI_CONTEXT_UNKNOWN: dict[str, Any] = {
    "output_status": "UNKNOWN", "current_stage": "UNKNOWN", "battery_type": "UNKNOWN",
    "mode": "UNKNOWN", "capacity_ah": "UNKNOWN", "capacity_known": False,
    "remaining_time": "—", "v_batt_now": None, "i_now": None,
    "temp_ext_now": None, "temp_int_now": None,
}

def _compat_float(value: Any, default: float = 0.0) -> float:
    if value is None or value in ("unknown", "unavailable", ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

async def build_ai_context_dict(
    source: OperatorReadSource,
    *,
    stage_snapshot: Callable[[float], Mapping[str, Any]],
    on_error: Callable[[Exception], None] | None = None,
) -> dict[str, Any]:
    """Build the legacy structured AI context from the explicit read boundary."""
    unknown = dict(_AI_CONTEXT_UNKNOWN)
    try:
        live = await source.read_live()
        controller = source.controller()
        snapshot = dict(stage_snapshot(_compat_float(live.get("temp_ext"))) or {})
        capacity = getattr(controller, "ah_capacity", 0) or 0
        capacity_known = float(capacity) > 0
        return {
            **unknown,
            "output_status": "ON" if str(live.get("switch", "")).lower() == "on" else "OFF",
            "current_stage": snapshot.get("stage", getattr(controller, "current_stage", "UNKNOWN")),
            "battery_type": snapshot.get("profile", getattr(controller, "battery_type", "UNKNOWN")),
            "mode": snapshot.get("phase", "UNKNOWN"),
            "capacity_ah": int(capacity) if capacity_known else "UNKNOWN",
            "capacity_known": capacity_known,
            "remaining_time": (snapshot.get("timers") or {}).get("remaining_time", "—"),
            "v_batt_now": _compat_float(live.get("battery_voltage")),
            "i_now": _compat_float(live.get("current")),
            "temp_ext_now": _compat_float(live.get("temp_ext")),
            "temp_int_now": _compat_float(live.get("temp_int")),
        }
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
        return unknown

async def build_ai_context_text(
    source: OperatorReadSource,
    *,
    stage_snapshot: Callable[[float], Mapping[str, Any]],
    recent_events: Callable[[int], Any],
    format_stage_snapshot: Callable[[Mapping[str, Any]], str],
    format_events: Callable[..., str],
    canonical_bool: Callable[[Mapping[str, Any], str], bool],
) -> str:
    """Build the legacy human-readable AI context from explicit read dependencies."""
    try:
        live = await source.read_live()
        controller = source.controller()

        v_out = _compat_float(live.get("voltage", 0.0))
        i_out = _compat_float(live.get("current", 0.0))
        p_out = _compat_float(live.get("power", 0.0))
        v_batt = _compat_float(live.get("battery_voltage", 0.0))
        ah = _compat_float(live.get("ah", 0.0))
        wh = _compat_float(live.get("wh", 0.0))
        v_set = _compat_float(live.get("set_voltage", 0.0))
        i_set = _compat_float(live.get("set_current", 0.0))

        output_on = str(live.get("switch", "")).lower() == "on"
        cv_mode = canonical_bool(live, "is_cv")
        cc_mode = canonical_bool(live, "is_cc")
        battery_mode = not output_on
        t_internal = _compat_float(live.get("temp_int", 0.0))
        t_external = _compat_float(live.get("temp_ext", 0.0))
        v_input = _compat_float(live.get("input_voltage", 0.0)) or 0.0
        uptime = live.get("uptime", "неизвестно")

        controller_info = ""
        capacity_known = False
        capacity_ah = 0
        important_events = recent_events(8)
        if bool(getattr(controller, "is_active", False)):
            timers = controller.get_timers()
            capacity_ah = int(getattr(controller, "ah_capacity", 0) or 0)
            capacity_known = capacity_ah > 0
            controller_info = f"""
Контроллер заряда:
- Активный этап: {controller.current_stage}
- Тип АКБ: {controller.battery_type}
- Заданная емкость: {capacity_ah}Ач
- Общее время: {timers['total_time']}
- Время этапа: {timers['stage_time']}
- Лимит этапа: {timers['remaining_time']}"""

        controller_snapshot = dict(stage_snapshot(t_external) or {})
        controller_info += f"""

Карточка стратегии:
{format_stage_snapshot(controller_snapshot)}"""
        if important_events:
            controller_info += f"""

Последние важные события:
{format_events(important_events, limit=8)}"""

        output_status = "ON" if output_on else "OFF"
        context = f"""ПОЛНЫЙ СЛЕПОК RD6018:

Статус выхода: {output_status} (включен/выключен)
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

Статусы:
- Выход включен: {'да' if output_on else 'нет'}
- Режим стабилизации напряжения: {'да' if cv_mode else 'нет'}
- Режим стабилизации тока: {'да' if cc_mode else 'нет'}
- Режим измерения АКБ: {'да' if battery_mode else 'нет'}

Температура:
- Температура блока: {t_internal:.1f}°C
- Температура АКБ: {t_external:.1f}°C

Система:
- Входное напряжение БП: {v_input:.1f}В
- Время работы: {uptime}{controller_info}"""

        tail_events = recent_events(5)
        if tail_events:
            context += "\n\nПоследние события:\n"
            for event in tail_events:
                context += f"- {event}\n"
        return context
    except Exception as exc:
        return f"Ошибка получения AI контекста: {exc}"

async def build_ai_analysis_text(
    source: OperatorReadSource,
    *,
    raw_history: Callable[..., Any],
    trend_summary: Callable[[Any, Any, Any], str],
    stage_snapshot: Callable[[float], Mapping[str, Any]],
    recent_events: Callable[[int], Any],
    ask_ai: Callable[[dict[str, Any]], Any],
    render_ai_text: Callable[[str], str],
    canonical_bool: Callable[[Mapping[str, Any], str], bool],
    on_error: Callable[[Exception], None] | None = None,
) -> str:
    """Build the legacy AI analysis payload without owning transport or UI routing."""
    try:
        history_result = raw_history(limit=50)
        if inspect.isawaitable(history_result):
            history_result = await history_result
        times, voltages, currents = history_result
        summary = trend_summary(times, voltages, currents)
        live = await source.read_live()
        controller = source.controller()
        is_cv = canonical_bool(live, "is_cv")
        is_cc = canonical_bool(live, "is_cc")
        mode_flags = "CV" if is_cv else ("CC" if is_cc else "-")
        capacity_ah = int(getattr(controller, "ah_capacity", 0) or 0)
        active = bool(getattr(controller, "is_active", False))
        capacity_known = bool(active and capacity_ah > 0)
        stage_remaining = "—"
        if active:
            try:
                stage_remaining = controller.get_timers().get("remaining_time", "—")
            except Exception:
                stage_remaining = "—"
        temp_ext_now = _compat_float(live.get("temp_ext", 0.0))
        controller_snapshot = dict(stage_snapshot(temp_ext_now) or {})
        events = recent_events(10)
        payload = {
            "times": times,
            "voltages": voltages,
            "currents": currents,
            "trend_summary": summary,
            "ai_context": {
                "output_status": "ON" if str(live.get("switch", "")).lower() == "on" else "OFF",
                "current_stage": getattr(controller, "current_stage", "Idle") if active else "Idle",
                "battery_type": getattr(controller, "battery_type", "UNKNOWN") if active else "UNKNOWN",
                "mode": mode_flags,
                "capacity_known": capacity_known,
                "capacity_ah": capacity_ah if capacity_known else "UNKNOWN",
                "remaining_time": stage_remaining,
                "v_batt_now": _compat_float(live.get("battery_voltage", 0.0)),
                "i_now": _compat_float(live.get("current", 0.0)),
                "temp_ext_now": temp_ext_now,
                "temp_int_now": _compat_float(live.get("temp_int", 0.0)),
            },
            "controller_snapshot": controller_snapshot,
            "recent_events": events,
        }
        result = ask_ai(payload)
        if inspect.isawaitable(result):
            result = await result
        return f"<b>🧠 AI Анализ</b>\n{render_ai_text(str(result))}"
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
        return "<b>🧠 AI Анализ</b>\n<i>Сервис временно недоступен, попробуйте позже.</i>"

def build_trend_summary(
    times: list[Any],
    voltages: list[Any],
    currents: list[Any],
    *,
    now: datetime | None = None,
) -> str:
    """Format the legacy compact telemetry trend for AI context."""
    if not times or not voltages or not currents:
        return ""
    now_value = datetime.now() if now is None else now
    n = min(len(times), len(voltages), len(currents))
    indices = [0, max(1, n // 3), max(2, 2 * n // 3), n - 1] if n >= 4 else list(range(n))
    lines: list[str] = []
    for index in indices:
        timestamp = times[index]
        voltage = voltages[index] if index < len(voltages) else 0.0
        current = currents[index] if index < len(currents) else 0.0
        try:
            observed_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")[:19])
            delta_min = int((now_value - observed_at).total_seconds() / 60)
            label = "сейчас" if delta_min < 1 else f"{delta_min} мин назад"
        except Exception:
            raw = str(timestamp)
            label = raw[-8:] if len(raw) >= 8 else "?"
        lines.append(f"{label}: {float(voltage):.2f}В, {float(current):.2f}А")
    return " | ".join(lines)
