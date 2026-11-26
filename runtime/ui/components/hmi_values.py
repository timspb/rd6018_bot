"""Pure HMI value normalization and formatting, no charger authority."""

from __future__ import annotations
import math
import re
import html
from typing import Any, Mapping, Optional, Protocol

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
    """Project the RD6018's native regulator mode; never infer from U/I."""
    from rd6018_telemetry import resolve_regulation, RegulationMode

    mode = resolve_regulation(live)
    if mode is RegulationMode.CV:
        return "CV"
    if mode is RegulationMode.CC:
        return "CC"
    return "—"


def _temperature(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}°C"


def _value(value: Optional[float], digits: int, suffix: str) -> str:
    return "—" if value is None else f"{value:.{digits}f} {suffix}"


def _duration(seconds: Any) -> str:
    value = _finite(seconds)
    if value is None:
        return "—"
    total = max(0, int(value))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


def format_operator_off_conditions(state: Any, *, now_s: float) -> str:
    """Render the existing operator OFF condition state without owning it."""
    if all(getattr(state, name) is None for name in (
        "voltage_ge", "voltage_le", "current_le", "current_ge", "time_sec",
    )):
        return ""
    parts = []
    if (
        state.voltage_ge is not None
        and state.voltage_le is not None
        and abs(state.voltage_ge - state.voltage_le) < 0.01
    ):
        parts.append(f"при достижении V {state.voltage_ge:.2f} В")
    else:
        if state.voltage_ge is not None:
            parts.append(f"при V≥{state.voltage_ge:.1f} В")
        if state.voltage_le is not None:
            parts.append(f"при V≤{state.voltage_le:.1f} В")

    if (
        state.current_le is not None
        and state.current_ge is not None
        and abs(state.current_le - state.current_ge) < 0.01
    ):
        parts.append(f"при достижении I {state.current_le:.2f} А")
    else:
        if state.current_le is not None:
            parts.append(f"при I≤{state.current_le:.2f} А")
        if state.current_ge is not None:
            parts.append(f"при I≥{state.current_ge:.2f} А")

    remaining_sec = 0.0
    if state.time_sec is not None:
        remaining_sec = state.start_time + state.time_sec - now_s
        if remaining_sec <= 0:
            parts.append("таймер истёк")
        else:
            h = int(state.time_sec // 3600)
            m = int((state.time_sec % 3600) // 60)
            parts.append(f"таймер {h}:{m:02d}")

    line = "⏹ ВЫКЛ ПО УСЛОВИЮ: " + ", ".join(parts)
    if state.time_sec is not None and remaining_sec > 0:
        h = int(remaining_sec // 3600)
        m = int((remaining_sec % 3600) // 60)
        line += f" | осталось до выкл: {h}:{m:02d}"
    return line

def _md_to_html(text: str) -> str:
    """Конвертировать **жирный** в <b>жирный</b> для Telegram HTML."""
    if not text:
        return text
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _sanitize_telegram_html(text: str) -> str:
    """Экранировать сырой HTML, оставляя только безопасные теги."""
    if not text:
        return text
    escaped = html.escape(text)
    allowed_tags = ("b", "i", "code", "pre")
    for tag in allowed_tags:
        escaped = escaped.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        escaped = escaped.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    escaped = escaped.replace("&lt;br&gt;", "<br>")
    escaped = escaped.replace("&lt;br/&gt;", "<br/>")
    escaped = escaped.replace("&lt;br /&gt;", "<br />")
    return escaped

def format_electrical_data(v: float, i: float, p: float = None, precision: int = 2) -> str:
    """Форматтер для электрических данных V/I/P с HTML-экранированием и точностью .2f."""
    # Разделитель между значениями — один пробел (без вертикальных черт).
    result = f"{v:.2f}В {i:.2f}А"  # Принудительно .2f для всех V/I
    if p is not None:
        result += f" {p:.1f}Вт"
    return html.escape(result)


def format_temperature_data(t_ext: float, t_int: float = None, warn_threshold: float = 50.0) -> str:
    """Форматтер для температурных данных с предупреждениями и HTML-экранированием."""
    parts = [f"🌡 АКБ {t_ext:.1f}°C"]
    if t_int is not None:
        block_part = f"БП {t_int:.1f}°C"
        if t_int > warn_threshold:
            block_part += " ⚠️"
        parts.append(block_part)
    return html.escape(" | ".join(parts))


def format_status_data(is_on: bool, mode: str, stage: str = None) -> str:
    """Форматтер для статусных данных с HTML-экранированием."""
    status_emoji = "⚡️" if is_on else "⏸️"
    result = f"{status_emoji}{mode}"
    if stage:
        result += f" {html.escape(stage)}"
    return result


def safe_html_format(template: str, **kwargs) -> str:
    """Безопасное форматирование HTML с экранированием переменных."""
    # Экранируем все переменные, кроме тех что уже содержат HTML теги
    safe_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, str) and ('<' in value or '>' in value or '&' in value):
            # Если значение уже содержит HTML теги, не экранируем
            if not any(tag in value for tag in ['<b>', '<i>', '<code>', '</b>', '</i>', '</code>']):
                safe_kwargs[key] = html.escape(value)
            else:
                safe_kwargs[key] = value
        else:
            safe_kwargs[key] = html.escape(str(value)) if value is not None else ""

    # Заменяем неподдерживаемые HTML теги на текстовые аналоги
    result = template.format(**safe_kwargs)
    result = result.replace('<hr>', '___________________')
    result = result.replace('<hr/>', '___________________')
    result = result.replace('<hr />', '___________________')

    return result


def build_legacy_dashboard_blocks(
    controller: Any,
    live: Mapping[str, Any],
    *,
    canonical_bool: Any,
    stage_label: Any,
    progress_line: Any,
    delta_i_exit: float,
    delta_v_exit: float,
) -> tuple[str, str, str, str, str]:
    """Render the legacy dashboard text blocks without owning charger state."""
    def number(value: Any, default: float = 0.0) -> float:
        parsed = _finite(value)
        return default if parsed is None else float(parsed)

    battery_v = number(live.get("battery_voltage"))
    set_v = number(live.get("set_voltage"))
    set_i = number(live.get("set_current"))
    is_on = str(live.get("switch", "")).lower() == "on"
    current = number(live.get("current"))
    temp_ext = number(live.get("temp_ext"))
    temp_int = number(live.get("temp_int"))
    ah = number(live.get("ah"))
    is_cv = bool(canonical_bool(live, "is_cv"))
    is_cc = bool(canonical_bool(live, "is_cc"))
    mode = "CV" if is_cv else ("CC" if is_cc else "-")

    active = bool(getattr(controller, "is_active", False))
    if active:
        timers = controller.get_timers()
        status_emoji = "🟢" if (is_on and current > 0.05) else "🟡"
        stage_name = html.escape(stage_label(controller.current_stage, short=True))
        battery_type = html.escape(controller.battery_type)
        total_time = html.escape(timers["total_time"])
        status_line = f"{status_emoji} Заряд: {stage_name} | {battery_type} | ⏱ {total_time}"
    else:
        status_line = f"⚪ Ожидание АКБ | Vакб {battery_v:.2f}В"

    idle_warning = ""
    if not active and is_on and current > 0.05:
        idle_warning = "🟡 Ручной режим: выход включен без автоэтапов"

    electrical_data = format_electrical_data(battery_v, current)
    temp_data = format_temperature_data(temp_ext, temp_int)
    live_line = f"⚡ LIVE: {mode} {electrical_data} {temp_data}"

    stage_block = ""
    if active:
        timers = controller.get_timers()
        stage_time = timers["stage_time"]
        current_v_set = number(live.get("set_voltage", set_v))
        current_i_set = number(live.get("set_current", set_i))
        transition_condition = ""
        raw_stage = controller.current_stage
        time_limit = timers["remaining_time"]

        if "Main" in raw_stage:
            if controller.battery_type == "Custom":
                transition_condition = "🔜 ФИНИШ: &lt;0.30А"
            elif controller.battery_type in ["Ca/Ca", "EFB"]:
                transition_condition = "🔜 ПЕРЕХОД: &lt;0.30А"
            elif controller.battery_type == "AGM":
                transition_condition = "🔜 ПЕРЕХОД: &lt;0.20А"
        elif "Mix" in raw_stage:
            v_max = controller.v_max_recorded
            i_min = controller.i_min_recorded
            if is_cv:
                if i_min is not None:
                    expect_i = i_min + delta_i_exit
                    transition_condition = f"🔜 ФИНИШ: ΔI +{delta_i_exit}А I≥{expect_i:.2f}А"
                else:
                    transition_condition = f"🔜 ФИНИШ: ΔI +{delta_i_exit}А"
            elif is_cc:
                if v_max is not None:
                    expect_v = v_max - delta_v_exit
                    transition_condition = f"🔜 ФИНИШ: ΔV −{delta_v_exit}В V≤{expect_v:.2f}В"
                else:
                    transition_condition = f"🔜 ФИНИШ: ΔV −{delta_v_exit}В"
            else:
                transition_condition = (
                    f"🔜 ФИНИШ: ΔV −{delta_v_exit}В (CC) "
                    f"или ΔI +{delta_i_exit}А (CV)"
                )
        elif "Десульфатация" in raw_stage:
            transition_condition = "🔜 ПЕРЕХОД: 2ч"
        elif "Безопасное ожидание" in raw_stage:
            transition_condition = "🔜 ПЕРЕХОД: падение V"
        elif "Остывание" in raw_stage:
            transition_condition = "🔜 ВОЗВРАТ: T&le;35°C"

        if time_limit != "—":
            try:
                if ":" in time_limit:
                    hours = int(time_limit.split(":")[0])
                    time_display = f"{hours}ч" if hours > 0 else "менее 1ч"
                else:
                    time_display = time_limit
            except Exception:
                time_display = time_limit
            if transition_condition:
                transition_condition = f"{transition_condition} | ⏱ {time_display}"
            else:
                transition_condition = f"🔜 ⏱ {time_display}"

        rendered_progress = progress_line(live)
        if rendered_progress:
            transition_condition = rendered_progress
        stage_name = html.escape(stage_label(controller.current_stage, short=False))
        stage_time_safe = html.escape(stage_time)
        stage_block = (
            f"\n📍 Этап: {stage_name} | ⏱ {stage_time_safe}\n"
            f"⚙ Уставки: {current_v_set:.2f}В | {current_i_set:.2f}А\n"
            f"{transition_condition}"
        )

    capacity_line = f"🔋 Емкость: {ah:.2f} Ач"
    return status_line, live_line, stage_block, capacity_line, idle_warning


def stage_label(raw_stage: str, short: bool = True) -> str:
    """Canonical legacy stage labels for compact/full operator projections."""
    stage = (raw_stage or "").strip()
    mapping_short = {
        "Main Charge": "Основной",
        "Mix Mode": "MIX",
        "Десульфатация": "Десульф",
        "Безопасное ожидание": "Ожидание",
        "Остывание": "Остывание",
        "Idle": "Ожидание",
    }
    mapping_full = {
        "Main Charge": "Основной заряд",
        "Mix Mode": "Микс-режим",
        "Десульфатация": "Десульфатация",
        "Безопасное ожидание": "Безопасное ожидание",
        "Остывание": "Остывание",
        "Idle": "Ожидание",
    }
    mapping = mapping_short if short else mapping_full
    return mapping.get(stage, stage)


class _StartFeedbackValue(Protocol):
    value: str


class _StartFeedbackExecution(Protocol):
    status: _StartFeedbackValue


class _StartFeedbackMode(Protocol):
    value: str


class _StartFeedbackPortResult(Protocol):
    mode: Optional[_StartFeedbackMode]
    execution_result: Optional[_StartFeedbackExecution]


class StartFeedbackResult(Protocol):
    """Read-only route outcome shape consumed by START presentation."""

    accepted: bool
    trace_id: str
    reason: str
    port_result: Optional[_StartFeedbackPortResult]


def format_start_feedback(result: StartFeedbackResult) -> str:
    """Describe the route result without confusing ACTIVE with DRY_RUN."""
    trace = result.trace_id[:8]
    if not result.accepted:
        return f"START отклонён: {result.reason}"

    port_result = result.port_result
    mode_value = port_result.mode if port_result is not None else None
    mode = mode_value.value if mode_value is not None else ""
    if mode == "active":
        execution = port_result.execution_result
        status_value = execution.status if execution is not None else None
        status = status_value.value if status_value is not None else "accepted"
        return f"✅ ACTIVE START {status}: {result.reason} ({trace})"
    if mode == "dry_run":
        return f"✅ START preflight PASS; DRY_RUN, заряд не запускался ({trace})"
    if mode:
        return f"✅ START {mode.upper()}: {result.reason} ({trace})"
    return f"✅ START принят: {result.reason} ({trace})"
