"""Read-only AUTO stage projection from existing controller/analyzer evidence.

No separate clock, charger authority, stage policy or stored state.
"""
from __future__ import annotations
from typing import Any, Mapping, Callable
from .hmi_values import _finite
from .hmi_compact import _durable_finish_status
from .hmi_mix_threshold import cv_delta_status, cc_delta_status
from .main_stage_progress import main_stage_countdown_status
from .mix_stage_progress import mix_finish_hold_status

def auto_stage_progress(
    app: Any, controller: Any, live: Mapping[str, Any], *,
    stage: str, regulator: str, telemetry_stale: bool,
    battery_type: str, capacity: float | None, now_s: Callable[[], float],
) -> tuple[str, str, Mapping[str, Any]]:
    progress = ""
    stage_status = ""
    snapshot: Mapping[str, Any] = {}
    progress_fn = getattr(app, "_format_stage_progress_line", None)
    if callable(progress_fn) and not telemetry_stale:
        try:
            progress = str(progress_fn(dict(live)) or "")
        except Exception:
            progress = ""
    try:
        snapshot = controller.ui_support_snapshot()
        metrics = dict(snapshot.get("metrics") or {})
        hold_started = snapshot.get("finish_hold_started_at")
        durable_status = _durable_finish_status(snapshot, regulator)
        in_mix = "mix" in stage.casefold()
        if stage == "Main Charge" and regulator == "CC":
            # Vmax/ΔV is MIX analysis, not a MAIN status indicator.
            stage_status = ""
        elif in_mix and hold_started is not None:
            from runtime.charge.runtime.support import _effective_mix_finish_hold_seconds
            stage_status = mix_finish_hold_status(
                snapshot=snapshot,
                started_at=hold_started,
                hold_seconds=_effective_mix_finish_hold_seconds(controller),
                now_s=now_s(),
            )
        elif durable_status is not None:
            stage_status = durable_status
        elif regulator in {"CV", "CC"} and not bool(
            snapshot.get(
                "runtime_evidence_available",
                snapshot.get("runtime_analysis_available", False),
            )
        ):
            stage_status = "⏳ Анализ Imin недоступен" if regulator == "CV" else "⏳ Анализ Vmax недоступен"
        elif regulator == "CV":
            minimum = _finite(metrics.get("current_min_a"))
            if minimum is None or minimum <= 0:
                stage_status = "⏳ Imin не достигнут"
            else:
                age = _finite(metrics.get("seconds_since_current_min"))
                elapsed = max(0, int(age or 0))
                minimum_started_at = _finite(metrics.get("current_min_started_at"))
                current_time = now_s()
                # Analyzer owns accepted Imin. Missing/invalid clock must
                # never masquerade as a freshly started three-hour hold.
                clock_available = age is not None and age >= 0
                if minimum_started_at is not None and 0 < minimum_started_at <= current_time:
                    elapsed = max(0, int(current_time - minimum_started_at))
                    clock_available = True
                hold_epoch = _finite(hold_started)
                if stage != "Main Charge" and hold_epoch is not None and 0 < hold_epoch <= current_time:
                    elapsed = max(0, int(current_time - hold_epoch))
                    clock_available = True
                if stage == "Main Charge":
                    stable_age = _finite(metrics.get("main_stable_hold_s"))
                    stability = metrics.get("main_stability_status")
                    if stability is not None:
                        elapsed = max(0, int(stable_age or 0))
                        clock_available = stable_age is not None and stable_age >= 0
                        stable_since = _finite(metrics.get("main_stable_since_s"))
                        if stability in {"holding", "candidate"} and stable_since is not None and 0 < stable_since <= current_time:
                            elapsed = max(0, int(current_time - stable_since))
                        else:
                            elapsed = 0
                    from runtime.charge.evidence.first_stage import tail_current_threshold_a
                    from runtime.charge.evidence.first_stage_variables import NEAR_TARGET_MARGIN_V
                    from runtime.charge.programs.native_recipe_session import native_target_parameters
                    from runtime.charge.strategy.main_variables import (
                        agm_tail_hold_seconds, standard_tail_hold_seconds,
                    )
                    hold_s = (agm_tail_hold_seconds() if battery_type == "AGM"
                              else standard_tail_hold_seconds())
                    hold_hours = _finite(native_target_parameters(controller, "MAIN_POLICY").get(
                        "tail_hold_hours", hold_s / 3600.0))
                    hold_s = hold_hours * 3600.0 if hold_hours is not None else None
                    current_now = _finite(live.get("current"))
                    voltage_now = _finite(live.get("battery_voltage"))
                    target_now = _finite(getattr(controller, "target_voltage", None))
                    if target_now is None:
                        target_now = _finite(live.get("set_voltage"))
                    tail_limit = (tail_current_threshold_a(battery_type, capacity)
                                  if capacity is not None and capacity > 0 else None)
                    ready = (
                        current_now is not None and voltage_now is not None
                        and target_now is not None and tail_limit is not None
                        and current_now <= tail_limit
                        and voltage_now >= target_now - float(NEAR_TARGET_MARGIN_V.default)
                    )
                    stage_status = main_stage_countdown_status(
                        minimum_a=minimum,
                        elapsed_s=elapsed,
                        clock_available=clock_available,
                        tail_ready=ready,
                        hold_seconds=hold_s,
                        intent=str(snapshot.get("intent") or ""),
                        chemistry=battery_type,
                    )
                    if stability in {"away_from_minimum", "rise_pending", "searching"}:
                        stage_status = (
                            f"Imin {minimum:.2f} A — выдержка 00:00; "
                            "ожидается устойчивое возвращение к минимуму"
                        )
                elif in_mix:
                    actual = _finite(metrics.get("delta_current_from_min_a"))
                    required = _finite(metrics.get("reversal_threshold_a"))
                    if actual is not None and required is not None and required > 0:
                        stage_status = cv_delta_status(minimum, actual, required)
                    else:
                        stage_status = f"📉 Imin {minimum:.2f} A · ожидание данных ΔI"
                elif not clock_available:
                    stage_status = f"⏳ Imin {minimum:.2f} A · время минимума не подтверждено"
                else:
                    stage_status = f"✅ Imin {minimum:.2f} A · ⏱ {elapsed // 3600}ч {(elapsed % 3600) // 60:02d}м"
        elif regulator == "CC":
            maximum = _finite(metrics.get("voltage_max_v"))
            if maximum is None or maximum <= 0:
                stage_status = "⏳ Vmax не достигнут"
            else:
                age = _finite(metrics.get("seconds_since_voltage_max"))
                elapsed = max(0, int(age)) if age is not None and age >= 0 else None
                started = _finite(hold_started)
                if started is not None:
                    current_time = now_s()
                    if 0 < started <= current_time:
                        elapsed = max(0, int(current_time - started))
                if in_mix:
                    actual = _finite(metrics.get("delta_voltage_from_max_v"))
                    required = _finite(metrics.get("voltage_reversal_threshold_v"))
                    if actual is not None and required is not None and required > 0:
                        stage_status = cc_delta_status(maximum, actual, required)
                    else:
                        stage_status = f"📈 Vmax {maximum:.2f} V · ожидание данных ΔV"
                elif elapsed is None:
                    stage_status = f"⏳ Vmax {maximum:.2f} V · время максимума не подтверждено"
                else:
                    stage_status = f"✅ Vmax {maximum:.2f} V · ⏱ {elapsed // 3600}ч {(elapsed % 3600) // 60:02d}м"
    except Exception:
        stage_status = ""
    return progress, stage_status, snapshot


def _compat_number(value: Any, default: float = 0.0) -> float:
    parsed = _finite(value)
    return default if parsed is None else float(parsed)


def format_stage_progress_line(
    controller: Any,
    live: Mapping[str, Any],
    *,
    stage_snapshot: Callable[[float], Mapping[str, Any]],
) -> str:
    """Render legacy dashboard stage progress from existing read-only evidence."""
    import html

    from rd6018_telemetry import as_bool
    from runtime.charge.strategy.exit_variables import MIX_CC_DELTA_V_EXIT_V
    from .stage_duration import format_eta_compact, format_seconds_compact

    if not bool(getattr(controller, "is_active", False)):
        return ""

    current_v = _compat_number(live.get("battery_voltage"))
    current_i = _compat_number(live.get("current"))
    temp_ext = _compat_number(live.get("temp_ext"))
    snapshot = dict(stage_snapshot(temp_ext) or {})
    timers = snapshot.get("timers") or {}
    hold = snapshot.get("hold") or {}
    is_cv = as_bool(live.get("is_cv")) is True
    is_cc = as_bool(live.get("is_cc")) is True
    stage = controller.current_stage
    remaining = format_eta_compact(timers.get("remaining_time", "—"))
    delta_v_exit = float(MIX_CC_DELTA_V_EXIT_V.default)

    def line(target: str, fact: str, rem: str, reached: bool, suffix: str = "") -> str:
        mark = "✅" if reached else "⚪"
        tail = f" {suffix}" if suffix else ""
        return f"🎯 {target} | {mark} {fact} | ⏳ {rem}{tail}"

    kind = str(hold.get("kind") or "").lower()
    if hold:
        if "low-current hold" in kind:
            threshold = _compat_number(hold.get("threshold_a"))
            target = f"I≤{threshold:.2f}A"
            fact = f"I {current_i:.2f}A"
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
            threshold_v = _compat_number(hold.get("threshold_v"))
            target = f"V≤{threshold_v:.2f}V"
            fact = f"V {current_v:.2f}V"
            reached = current_v <= threshold_v
            return line(target, fact, html.escape(str(hold.get("remaining_text") or remaining)), reached, "до выхода")

        if stage == controller.STAGE_MIX:
            policy = snapshot.get("mix_exit_policy") or {}
            mix_delta = controller._mix_current_delta_threshold()
            if controller.finish_timer_start is not None:
                if is_cv and controller.i_min_recorded is not None:
                    delta_now = max(0.0, current_i - controller.i_min_recorded)
                    fact = f"ΔI {delta_now:.3f}A"
                    reached = controller._exit_cv_condition(current_i)
                    return line(f"ΔI≥{mix_delta:.2f}A", fact, remaining, reached, "до SAFE_WAIT")
                if is_cc and controller.v_max_recorded is not None:
                    delta_now = max(0.0, controller.v_max_recorded - current_v)
                    fact = f"ΔV {delta_now:.3f}V"
                    reached = controller._exit_cc_condition(current_v)
                    return line(f"ΔV≥{delta_v_exit:.2f}V", fact, remaining, reached, "до SAFE_WAIT")
            return line("Δ подтверждена", "таймер 2ч", remaining, True, "до SAFE_WAIT")

        if is_cv:
            base_i = controller.i_min_recorded if controller.i_min_recorded is not None else current_i
            delta_now = max(0.0, current_i - base_i)
            mix_delta = controller._mix_current_delta_threshold()
            target = f"ΔI≥{mix_delta:.2f}A"
            fact = f"ΔI {delta_now:.3f}A"
            reached = controller._exit_cv_condition(current_i)
        elif is_cc:
            base_v = controller.v_max_recorded if controller.v_max_recorded is not None else current_v
            delta_now = max(0.0, base_v - current_v)
            target = f"ΔV≥{delta_v_exit:.2f}V"
            fact = f"ΔV {delta_now:.3f}V"
            reached = controller._exit_cc_condition(current_v)
        else:
            mix_delta = controller._mix_current_delta_threshold()
            target = f"ΔV≥{delta_v_exit:.2f}V / ΔI≥{mix_delta:.2f}A"
            fact = f"V {current_v:.2f}V, I {current_i:.2f}A"
            reached = False

        fallback_hours = policy.get("fallback_limit_hours")
        if isinstance(fallback_hours, (int, float)):
            fallback_text = f"{int(fallback_hours)}ч" if float(fallback_hours).is_integer() else f"{fallback_hours:.1f}ч"
        else:
            fallback_text = remaining
        return line(target, fact, fallback_text or remaining, reached, "лимит")

    if stage == controller.STAGE_COOLING:
        return line("T≤35°C", f"АКБ {temp_ext:.1f}°C", "возврат после остывания", temp_ext <= 35.0)

    if stage == controller.STAGE_DESULFATION:
        return line(
            "2ч",
            html.escape(str(timers.get("stage_time", "—"))),
            html.escape(str(timers.get("remaining_time", "—"))),
            False,
            "до SAFE_WAIT",
        )

    return ""
