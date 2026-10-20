"""Common runtime mechanics for an authoritative MAIN tick.

This is a transitional runtime adapter while the controller object is being
decomposed. It deliberately contains no MAIN transition decision. MAIN
transitions are evaluated later by runtime.charge.strategy.main_authority.

Unlike the historical scaffold, this function never calls the historical
ChargeController.tick and never masks stage clocks or blanking timers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from runtime.charge.runtime.variables import (
    HISTORY_SAMPLE_INTERVAL_S,
    OPERATOR_REPORT_INTERVAL_S,
    STAGE_CLOCK_SANITY_MAX_HOURS,
)
from runtime.charge.strategy.main_variables import main_fallback_seconds
from runtime.safety.communication_variables import (
    LINK_LOSS_INITIAL_NOTICE_COUNT,
    LINK_LOSS_NOTICE_INTERVAL_S,
)
from runtime.safety.thermal_variables import (
    BATTERY_TEMP_CRITICAL_C,
    BATTERY_TEMP_PAUSE_C,
    BATTERY_TEMP_WARNING_C,
)
from runtime.safety.voltage_variables import PB_PROFILE_WARNING_VOLTAGE_V


logger = logging.getLogger("rd6018.charge.main_runtime")


def apply_main_authority_tick(
    host: Any, *, record: Any, first_stage: Any, timestamp_s: float,
    voltage: float, current: float, temp: float, ah: float,
    is_cv: bool, actions: Dict[str, Any], decision_veto=None,
) -> Any:
    """Own MAIN transition evaluation and dispatch into typed stage effects."""
    from runtime.charge.decisions import AuthorityAction, AuthorityDecision
    from runtime.charge.runtime.agm_step_advance import (
        apply_agm_step_advance_effect, build_agm_step_advance_effect,
    )
    from runtime.charge.runtime.desulfation_entry import apply_main_desulfation_entry
    from runtime.charge.runtime.final_safe_wait_entry import apply_main_completion_to_safe_wait
    from runtime.charge.runtime.mix_entry import apply_main_mix_entry
    from runtime.charge.runtime.stop_diagnose import apply_stop_and_diagnose
    from runtime.charge.strategy.main_authority import decide_main_transition
    from runtime.charge.strategy.main_variables import (
        AGM_MAX_RECOVERY_ATTEMPTS, AGM_STAGE_VOLTAGES_V,
        STANDARD_MAX_RECOVERY_ATTEMPTS, agm_tail_hold_seconds,
        main_fallback_seconds, standard_tail_hold_seconds,
    )

    required_hold = (
        agm_tail_hold_seconds()
        if host.battery_type == host.PROFILE_AGM
        else standard_tail_hold_seconds()
    )
    max_desulf = (
        int(AGM_MAX_RECOVERY_ATTEMPTS.default)
        if host.battery_type == host.PROFILE_AGM
        else int(STANDARD_MAX_RECOVERY_ATTEMPTS.default)
    )
    decision = decide_main_transition(
        profile=host.battery_type,
        intent=host._v2_intent,
        first_stage=first_stage,
        policy_decision=record.decision.decision,
        seconds_since_current_min=record.analysis.metrics.seconds_since_current_min,
        required_tail_hold_s=required_hold,
        agm_stage_idx=host._agm_stage_idx,
        agm_stage_count=len(AGM_STAGE_VOLTAGES_V.default),
        desulf_attempts=host.antisulfate_count,
        max_desulf_attempts=max_desulf,
        main_elapsed_s=max(0.0, float(timestamp_s) - float(host.stage_start_time)),
        main_limit_s=main_fallback_seconds(),
        current_a=float(current),
        is_cv=bool(is_cv),
    )
    if decision_veto is not None:
        veto = decision_veto(decision)
        if veto is not None:
            apply_stop_and_diagnose(
                host, actions=actions, now=timestamp_s, voltage=voltage,
                current=current, temp=temp, ah=ah, reason=veto.reason,
            )
            return veto
    if decision.action == AuthorityAction.ADVANCE_AGM_STEP:
        effect = build_agm_step_advance_effect(
            current_stage_index=host._agm_stage_idx,
            stage_count=len(AGM_STAGE_VOLTAGES_V.default),
            now_s=timestamp_s, ah=ah, temperature_c=temp,
            reason=decision.reason,
        )
        apply_agm_step_advance_effect(host, effect, actions)
    elif decision.action == AuthorityAction.ENTER_DESULFATION:
        target_v, target_i = host._desulf_target(temp)
        apply_main_desulfation_entry(
            host, reason=decision.reason, now_s=timestamp_s, ah=ah,
            voltage_v=voltage, current_a=current, temperature_c=temp,
            target_voltage_v=target_v, target_current_a=target_i, actions=actions,
        )
    elif decision.action == AuthorityAction.ENTER_MIX:
        target_v, target_i = host._mix_target(temp)
        limits: Dict[str, Any] = {}
        host._add_phase_limits(limits, target_v, target_i)
        apply_main_mix_entry(
            host, reason=decision.reason, now_s=timestamp_s, ah=ah,
            voltage_v=voltage, current_a=current, temperature_c=temp,
            target_voltage_v=target_v, target_current_a=target_i,
            ovp_v=limits["set_ovp"], ocp_a=limits["set_ocp"], actions=actions,
        )
    elif decision.action == AuthorityAction.COMPLETE_TO_SAFE_WAIT:
        target_v, target_i = host._storage_target()
        if not apply_main_completion_to_safe_wait(
            host, now_s=timestamp_s, voltage_v=voltage, current_a=current,
            temperature_c=temp, ah=ah, reason=decision.reason,
            target_voltage_v=target_v, target_current_a=target_i, actions=actions,
        ):
            reason = "final_safe_wait_entry_session_identity_invalid"
            apply_stop_and_diagnose(
                host, actions=actions, now=timestamp_s, voltage=voltage,
                current=current, temp=temp, ah=ah, reason=reason,
            )
            return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, reason)
    elif decision.action == AuthorityAction.STOP_AND_DIAGNOSE:
        apply_stop_and_diagnose(
            host, actions=actions, now=timestamp_s, voltage=voltage,
            current=current, temp=temp, ah=ah, reason=decision.reason,
        )
    return decision


def _output_is_known(value: Any) -> bool:
    return value is not None and str(value).lower() not in {
        "unavailable",
        "unknown",
        "",
    }


def _output_is_on(value: Any) -> bool:
    return value is True or str(value).lower() == "on"


def _phase_log(phase: str, voltage: float, current: float, temp: float) -> None:
    try:
        from time_utils import format_time_user_tz

        stamp = format_time_user_tz()
    except Exception:
        stamp = "-"
    logger.info(
        "%s | %-12s | %5.2fВ | %5.2fА | %5.1f°C",
        stamp,
        phase,
        voltage,
        current,
        temp,
    )


async def run_authoritative_main_scaffold(
    host: Any,
    *,
    voltage: float,
    current: float,
    temp_ext: Optional[float],
    is_cv: bool,
    ah: float,
    output_is_on: Optional[Any],
    manual_off_active: bool,
    is_cc: Optional[bool],
    manual_active: bool,
    now_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Run accepted common safety/bookkeeping mechanics for MAIN only.

    The host is transitional controller state. This function owns no Telegram,
    transport or physical write; it only mutates in-memory charge runtime state
    and returns the same action dictionary consumed by the execution layer.
    """
    actions: Dict[str, Any] = {}
    resolved_is_cc = not bool(is_cv) if is_cc is None else bool(is_cc)
    host.is_cv = bool(is_cv)
    host.is_cc = resolved_is_cc
    now = float(time.time() if now_s is None else now_s)
    host.last_update_time = now

    if temp_ext is None or temp_ext in ("unavailable", "unknown", ""):
        host._was_unavailable = True
        host._link_lost_at = now
        actions["emergency_stop"] = True
        actions["log_event"] = "EMERGENCY_UNAVAILABLE"
        if host._last_known_output_on:
            should_notify = (
                host._link_loss_notice_count
                < int(LINK_LOSS_INITIAL_NOTICE_COUNT.default)
                or now - host._link_loss_last_notice_at
                >= float(LINK_LOSS_NOTICE_INTERVAL_S.default)
            )
            if should_notify:
                host._link_loss_notice_count += 1
                host._link_loss_last_notice_at = now
                msg = "⚠️ Связь потеряна во время заряда!"
                actions["notify"] = msg
                host.notify(msg)
            if host.is_active:
                host.stop(clear_session=False)
        else:
            host.stop(clear_session=False)
        return actions

    try:
        temp = float(temp_ext)
    except (ValueError, TypeError):
        msg = (
            "🔴 <b>АВАРИЯ:</b> Некорректные данные датчика температуры. "
            "Заряд остановлен в целях безопасности."
        )
        actions.update(
            emergency_stop=True,
            full_reset=True,
            notify=msg,
            log_event="EMERGENCY_TEMP_INVALID",
        )
        host.notify(msg)
        return actions

    critical = float(BATTERY_TEMP_CRITICAL_C.default)
    pause = float(BATTERY_TEMP_PAUSE_C.default)
    warning = float(BATTERY_TEMP_WARNING_C.default)

    if temp >= critical:
        msg = (
            "🔴 <b>КРИТИЧЕСКИЙ ПЕРЕГРЕВ в режиме!</b>\n"
            f"Температура: {temp:.1f}°C (критическая: {critical:.1f}°C)\n"
            "Заряд экстренно остановлен и сброшен!"
        )
        actions.update(
            emergency_stop=True,
            full_reset=True,
            notify=msg,
            log_event=f"EMERGENCY_TEMP_CRITICAL: {temp:.1f}°C >= {critical:.1f}°C",
        )
        host.notify(msg)
        return actions

    if temp >= pause:
        actions["log_event_end"] = {
            "stage": host.current_stage,
            "time_sec": now - host.stage_start_time,
            "ah_on_stage": ah - host._stage_start_ah,
            "ah": ah,
            "t": temp,
            "v": voltage,
            "i": current,
            "trigger": f"T≥{pause:g}°C ({temp:.1f}°C)",
        }
        cooling_target_v, cooling_target_i = host._main_target(temp)
        previous_stage = host.current_stage
        host.current_stage = host.STAGE_COOLING
        host._clear_restored_targets()
        host.stage_start_time = now
        host._stage_start_ah = ah
        host._cooling_from_stage = previous_stage
        host._cooling_target_v = cooling_target_v
        host._cooling_target_i = cooling_target_i
        msg = (
            "🌡 <b>ПЕРЕГРЕВ - ПАУЗА ЗАРЯДА!</b>\n"
            f"Температура: {temp:.1f}°C (лимит: {pause:g}°C)\n"
            f"Выход отключен. Ожидание охлаждения до {warning:g}°C."
        )
        actions.update(turn_off=True, notify=msg, log_event="START")
        host.notify(msg)
        return actions

    host._mark_stage_sample(voltage, current, temp, ah)

    if _output_is_known(output_is_on):
        host._last_known_output_on = _output_is_on(output_is_on)
    if host._was_unavailable:
        host._link_loss_notice_count = 0
        host._link_loss_last_notice_at = 0.0
        host._link_lost_at = 0.0
    host._was_unavailable = False

    host._analytics_history.append((now, voltage, current, ah, temp))
    if now - host._last_v_i_history_time >= float(HISTORY_SAMPLE_INTERVAL_S.default):
        host.v_history.append((now, voltage))
        host.i_history.append((now, current))
        host._last_v_i_history_time = now

    elapsed_check = now - host.stage_start_time
    if elapsed_check < 0 or elapsed_check > float(STAGE_CLOCK_SANITY_MAX_HOURS.default) * 3600.0:
        host.stage_start_time = now
        logger.warning("MAIN runtime: stage_start_time corrected (elapsed invalid)")

    if host.emergency_hv_disconnect:
        host.notify(
            "🔴 <b>АВАРИЙНОЕ ОТКЛЮЧЕНИЕ:</b> "
            "Потеряна связь с контроллером при высоком напряжении (>15В)!"
        )
        host.emergency_hv_disconnect = False

    if temp >= warning and not host._temp_warning_alerted:
        host._temp_warning_alerted = True
        host._pending_log_event = "WARNING_35C"
        host.notify(
            f"⚠️ Внимание: Температура АКБ поднялась до {temp:.1f}°C. "
            f"При {pause:g}°C заряд будет приостановлен."
        )

    if voltage > float(PB_PROFILE_WARNING_VOLTAGE_V.default) and not manual_active:
        actions["notify"] = (
            f"<b>⚠️ Напряжение</b> {voltage:.2f}V превышает лимит!"
        )

    if host._pending_log_event:
        actions["log_event"] = host._pending_log_event
        host._pending_log_event = None

    elapsed = now - host.stage_start_time
    if now - host._last_log_time >= float(HISTORY_SAMPLE_INTERVAL_S.default):
        _phase_log(host.current_stage, voltage, current, temp)
        host._last_log_time = now

    report_interval = float(OPERATOR_REPORT_INTERVAL_S.default)
    if not manual_off_active and now - host._last_hourly_report >= report_interval:
        host._last_hourly_report = now
        current_hrs = elapsed / 3600.0
        max_hrs = main_fallback_seconds() / 3600.0
        report = (
            f"⏳ Прошло {current_hrs:.1f}ч из {max_hrs:.0f} лимита этапа. "
            f"Ток: {current:.2f} А, T: {temp:.1f}°C, Ah: {ah:.2f}."
        )
        if "notify" not in actions or not actions["notify"]:
            actions["notify"] = report
        else:
            host.notify(report)

    if is_cv:
        if host._cv_since is None:
            host._cv_since = now
    else:
        host._cv_since = None

    if host._stage_start_ah == 0:
        host._stage_start_ah = ah
        if "log_event" not in actions:
            actions["log_event"] = (
                f"START | Емкость: {host.ah_capacity}Ah | profile={host.battery_type}"
            )

    return actions


__all__ = ["run_authoritative_main_scaffold"]
