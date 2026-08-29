from __future__ import annotations

import html
import math
from typing import Any, Mapping, Optional

from pb_domain import ChargeIntent
from v2_ui import INTENT_LABELS


_DECISION_LABELS = {
    "finish_stage": "🎯 Финиш подтверждён",
    "hold_output_off": "⛔ Выход удерживается OFF",
    "rest_and_diagnose": "🧪 Пауза и диагностика",
    "pause_thermal": "🌡 Термопауза",
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
    raw = str(snapshot.get("intent") or ChargeIntent.RECOVERY.value)
    try:
        return INTENT_LABELS[ChargeIntent(raw)]
    except (ValueError, KeyError):
        return raw


def _temperature_line(metrics: Mapping[str, Any]) -> Optional[str]:
    trend = _finite(metrics.get("d_temp_c_per_min"))
    if trend is None:
        return None
    if abs(trend) < 0.03:
        return "🌡 Температура стабильна"
    arrow = "↗" if trend > 0 else "↘"
    return f"🌡 {arrow} {trend:+.02f} °C/мин"


def _current_direction(metrics: Mapping[str, Any]) -> str:
    rate = _finite(metrics.get("d_current_a_per_min"))
    if rate is None:
        return "Хвост ещё не сформирован"
    if rate < -0.003:
        return "Ток снижается · хвост формируется"
    if rate > 0.003:
        return "Ток растёт · наблюдаем контекст U/T"
    return "Ток стабилен · формируется полка"


def _voltage_direction(metrics: Mapping[str, Any]) -> str:
    rate = _finite(metrics.get("d_voltage_v_per_min"))
    if rate is None:
        return "Пик напряжения ещё не сформирован"
    if rate > 0.003:
        return "Напряжение растёт · ищем Vmax"
    if rate < -0.003:
        return "Напряжение снижается · проверяем ΔV"
    return "Напряжение стабильно · формируется пик"


def format_active_evidence_pretty(
    snapshot: Mapping[str, Any],
    *,
    voltage_v: Optional[float] = None,
    current_a: Optional[float] = None,
    temp_c: Optional[float] = None,
) -> str:
    """Human-first compact evidence block for the main Telegram dashboard.

    Live V/I/T are already shown immediately above this block by the dashboard, so
    they are intentionally not repeated here.  Raw rates, thresholds and internal
    decision names remain available on the detailed V2/full-info surfaces.
    """

    del voltage_v, current_a, temp_c
    metrics = dict(snapshot.get("metrics") or {})
    lines = [f"{html.escape(_intent_text(snapshot))} · <b>V2</b>"]

    if not snapshot.get("authoritative"):
        lines.append("⚠️ Legacy fallback authority")

    is_cv = bool(snapshot.get("is_cv"))
    is_cc = bool(snapshot.get("is_cc"))

    if is_cv:
        imin = _finite(metrics.get("current_min_a"))
        age = _duration(metrics.get("seconds_since_current_min"))
        delta = _finite(metrics.get("delta_current_from_min_a"))
        threshold = _finite(metrics.get("reversal_threshold_a"))

        # Zero is not useful Imin evidence for an energized Pb charge stage.  It can
        # appear briefly around startup/arming and must not be rendered as a real
        # electrochemical minimum.
        if imin is None or imin <= 0:
            lines.append("🟢 <b>CV</b> · Imin: <b>ищем…</b>")
            lines.append(_current_direction(metrics))
        else:
            lines.append(f"🟢 <b>CV</b> · Imin <b>{imin:.3f} A</b>")
            if delta is not None and threshold is not None:
                age_text = f" · {age}" if age else ""
                lines.append(
                    f"ΔI <b>{delta:+.3f}</b> / {threshold:.3f} A{age_text}"
                )
    elif is_cc:
        vmax = _finite(metrics.get("voltage_max_v"))
        age = _duration(metrics.get("seconds_since_voltage_max"))
        delta = _finite(metrics.get("delta_voltage_from_max_v"))
        threshold = _finite(metrics.get("voltage_reversal_threshold_v"))

        if vmax is None or vmax <= 0:
            lines.append("🟠 <b>CC</b> · Vmax: <b>ищем…</b>")
            lines.append(_voltage_direction(metrics))
        else:
            lines.append(f"🟠 <b>CC</b> · Vmax <b>{vmax:.3f} V</b>")
            if delta is not None and threshold is not None:
                age_text = f" · {age}" if age else ""
                lines.append(
                    f"ΔV <b>{delta:+.3f}</b> / {threshold:.3f} V{age_text}"
                )
    else:
        lines.append("⚪ Режим регулятора определяется…")

    temp_line = _temperature_line(metrics)
    if temp_line:
        lines.append(temp_line)

    if snapshot.get("finish_hold_started_at") is not None:
        lines.append("🎯 Δ подтверждена · <b>выдержка 2ч</b>")
    else:
        decision = str(snapshot.get("decision") or "continue")
        decision_line = _DECISION_LABELS.get(decision)
        if decision_line:
            lines.append(decision_line)

    return "\n".join(lines)


def install_dashboard_polish(app: Any, ui_module: Any) -> None:
    """Install presentation-only V2 polish over the preserved legacy dashboard."""

    # The V2 adapter resolves this module global at callback/render time, so replacing
    # it here changes presentation only; control/evidence generation is untouched.
    ui_module.format_active_evidence = format_active_evidence_pretty

    original_caption = app._compact_dashboard_caption

    def _compact_dashboard_caption(live, chart_mode: str, mode: str, idle_warning: str) -> str:
        text = original_caption(live, chart_mode, mode, idle_warning)
        if not app.charge_controller.is_active:
            return text
        if app.charge_controller.current_stage not in {
            app.charge_controller.STAGE_MAIN,
            app.charge_controller.STAGE_MIX,
        }:
            return text

        # Main/Mix already display the regulator mode inside the V2 evidence block.
        # Remove the legacy "Режим ... Лимит этапа ..." line from the mobile card:
        # the hard limit is a safety deadline, not ETA, and remains in Full info.
        return "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("Режим:")
        )

    app._compact_dashboard_caption = _compact_dashboard_caption
