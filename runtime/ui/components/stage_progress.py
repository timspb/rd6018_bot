"""Pure rendering for the compact legacy operator stage progress line."""

from __future__ import annotations

import html
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_eta_compact(raw_eta: Any) -> str:
    """Format the existing strategy ETA for a narrow dashboard."""
    value = str(raw_eta or "").strip()
    if not value or value == "—":
        return "—"
    if ":" in value:
        parts = value.split(":")
        if len(parts) == 2:
            try:
                hours, minutes = int(parts[0]), int(parts[1])
                return f"{hours}ч {minutes:02d}м" if hours > 0 else f"{minutes}м"
            except ValueError:
                return value
    return value


def format_seconds_compact(seconds: Any) -> str:
    """Format a duration without owning or deriving a clock."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "—"
    if total <= 0:
        return "0м"
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}ч {minutes:02d}м"
    if hours:
        return f"{hours}ч"
    return f"{max(1, minutes)}м"


def render_stage_progress_line(context: Mapping[str, Any]) -> str:
    """Render an already-read controller snapshot and telemetry values."""
    if not context.get("is_active"):
        return ""

    snapshot = context.get("snapshot") or {}
    timers = snapshot.get("timers") or {}
    hold = snapshot.get("hold") or {}
    current_v = context["current_v"]
    current_i = context["current_i"]
    temp_ext = context["temp_ext"]
    stage = context["stage"]
    remaining = format_eta_compact(timers.get("remaining_time", "—"))

    def line(target: str, fact: str, rem: str, reached: bool, suffix: str = "") -> str:
        mark = "✅" if reached else "⚪"
        tail = f" {suffix}" if suffix else ""
        return f"🎯 {target} | {mark} {fact} | ⏳ {rem}{tail}"

    kind = str(hold.get("kind") or "").lower()
    if hold:
        if "low-current hold" in kind:
            threshold = _safe_float(hold.get("threshold_a"))
            target, fact = f"I≤{threshold:.2f}A", f"I {current_i:.2f}A"
            reached = bool(hold.get("active")) or current_i <= threshold
            if reached:
                return line(target, fact, html.escape(str(hold.get("remaining_text") or remaining)), True, "до Mix")
            return line(target, fact, format_seconds_compact(hold.get("required_sec")), False, "hold")

        if "desulf timer" in kind:
            fact = html.escape(str(hold.get("elapsed_text") or timers.get("stage_time", "—")))
            return line("2ч", fact, html.escape(str(hold.get("remaining_text") or remaining)), False, "до SAFE_WAIT")

        if "mix delta timer" in kind:
            fact = html.escape(str(hold.get("elapsed_text") or timers.get("stage_time", "—")))
            return line("Δ подтверждена", f"таймер {fact}", html.escape(str(hold.get("remaining_text") or remaining)), True, "до SAFE_WAIT")

        if "safe wait" in kind:
            threshold_v = _safe_float(hold.get("threshold_v"))
            return line(f"V≤{threshold_v:.2f}V", f"V {current_v:.2f}V", html.escape(str(hold.get("remaining_text") or remaining)), current_v <= threshold_v, "до выхода")

        if stage == context["stage_mix"]:
            policy = snapshot.get("mix_exit_policy") or {}
            mix_delta = context["mix_current_delta_threshold"]
            if context["finish_timer_active"]:
                if context["is_cv"] and context["i_min_recorded"] is not None:
                    delta_now = max(0.0, current_i - context["i_min_recorded"])
                    return line(f"ΔI≥{mix_delta:.2f}A", f"ΔI {delta_now:.3f}A", remaining, context["exit_cv_reached"], "до SAFE_WAIT")
                if context["is_cc"] and context["v_max_recorded"] is not None:
                    delta_now = max(0.0, context["v_max_recorded"] - current_v)
                    return line(f"ΔV≥{context['delta_v_exit']:.2f}V", f"ΔV {delta_now:.3f}V", remaining, context["exit_cc_reached"], "до SAFE_WAIT")
            return line("Δ подтверждена", "таймер 2ч", remaining, True, "до SAFE_WAIT")

        if context["is_cv"]:
            base_i = context["i_min_recorded"] if context["i_min_recorded"] is not None else current_i
            delta_now = max(0.0, current_i - base_i)
            mix_delta = context["mix_current_delta_threshold"]
            target, fact, reached = f"ΔI≥{mix_delta:.2f}A", f"ΔI {delta_now:.3f}A", context["exit_cv_reached"]
        elif context["is_cc"]:
            base_v = context["v_max_recorded"] if context["v_max_recorded"] is not None else current_v
            delta_now = max(0.0, base_v - current_v)
            target, fact, reached = f"ΔV≥{context['delta_v_exit']:.2f}V", f"ΔV {delta_now:.3f}V", context["exit_cc_reached"]
        else:
            mix_delta = context["mix_current_delta_threshold"]
            target = f"ΔV≥{context['delta_v_exit']:.2f}V / ΔI≥{mix_delta:.2f}A"
            fact, reached = f"V {current_v:.2f}V, I {current_i:.2f}A", False

        fallback_hours = policy.get("fallback_limit_hours")
        if isinstance(fallback_hours, (int, float)):
            fallback_text = f"{int(fallback_hours)}ч" if float(fallback_hours).is_integer() else f"{fallback_hours:.1f}ч"
        else:
            fallback_text = remaining
        return line(target, fact, fallback_text or remaining, reached, "лимит")

    if stage == context["stage_cooling"]:
        return line("T≤35°C", f"АКБ {temp_ext:.1f}°C", "возврат после остывания", temp_ext <= 35.0)
    if stage == context["stage_desulfation"]:
        return line("2ч", html.escape(str(timers.get("stage_time", "—"))), html.escape(str(timers.get("remaining_time", "—"))), False, "до SAFE_WAIT")
    return ""
