"""Runtime owner for residual automatic PREP/COOLING/IDLE/DONE stages.

These stages are intentionally narrow.  Common safety/bookkeeping mirrors the
already-migrated automatic scaffolds, while stage transitions remain explicit
here so production never needs historical ChargeController.tick().
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from runtime.charge.runtime.variables import (
    HISTORY_SAMPLE_INTERVAL_S,
    OPERATOR_REPORT_INTERVAL_S,
    STAGE_CLOCK_SANITY_MAX_HOURS,
    STAGE_TRANSITION_BLANKING_S,
)
from runtime.charge.strategy.prep_variables import PREP_VOLTAGE_V
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


logger = logging.getLogger("rd6018.charge.residual_runtime")


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


async def run_authoritative_residual_scaffold(
    host: Any,
    *,
    stage_before: str,
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
    """Run PREP/COOLING/IDLE/DONE without historical FSM execution."""

    actions: Dict[str, Any] = {}
    resolved_is_cc = not bool(is_cv) if is_cc is None else bool(is_cc)
    host.is_cv = bool(is_cv)
    host.is_cc = resolved_is_cc
    now = float(time.time() if now_s is None else now_s)
    host.last_update_time = now

    if stage_before not in {
        host.STAGE_PREP,
        host.STAGE_COOLING,
        host.STAGE_IDLE,
        host.STAGE_DONE,
    }:
        raise ValueError(f"unsupported residual stage: {stage_before}")

    if temp_ext is None or temp_ext in ("unavailable", "unknown", ""):
        host._was_unavailable = True
        host._link_lost_at = now
        actions["emergency_stop"] = True
        actions["log_event"] = "EMERGENCY_UNAVAILABLE"
        if host._last_known_output_on:
            should_notify = (
                host._link_loss_notice_count < int(LINK_LOSS_INITIAL_NOTICE_COUNT.default)
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

    if (
        temp >= pause
        and stage_before not in {host.STAGE_COOLING, host.STAGE_IDLE, host.STAGE_DONE}
    ):
        actions["log_event_end"] = host._make_log_event_end(
            now,
            ah,
            voltage,
            current,
            temp,
            f"T≥{pause:g}°C ({temp:.1f}°C)",
        )
        if stage_before == host.STAGE_PREP:
            cooling_target_v, cooling_target_i = host._prep_target(temp)
        else:  # defensive only; supported active residual stage is PREP.
            cooling_target_v, cooling_target_i = host._get_current_targets(temp)
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

    if stage_before != host.STAGE_IDLE:
        host._analytics_history.append((now, voltage, current, ah, temp))
        if now - host._last_v_i_history_time >= float(HISTORY_SAMPLE_INTERVAL_S.default):
            host.v_history.append((now, voltage))
            host.i_history.append((now, current))
            host._last_v_i_history_time = now

        elapsed_check = now - host.stage_start_time
        if (
            elapsed_check < 0
            or elapsed_check > float(STAGE_CLOCK_SANITY_MAX_HOURS.default) * 3600.0
        ):
            host.stage_start_time = now
            logger.warning("residual runtime: stage_start_time corrected (elapsed invalid)")

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
        actions["notify"] = f"<b>⚠️ Напряжение</b> {voltage:.2f}V превышает лимит!"

    if stage_before == host.STAGE_IDLE:
        return actions

    if host._pending_log_event:
        actions["log_event"] = host._pending_log_event
        host._pending_log_event = None

    elapsed = max(0.0, now - host.stage_start_time)
    if now - host._last_log_time >= float(HISTORY_SAMPLE_INTERVAL_S.default):
        _phase_log(host.current_stage, voltage, current, temp)
        host._last_log_time = now

    if (
        not manual_off_active
        and now - host._last_hourly_report >= float(OPERATOR_REPORT_INTERVAL_S.default)
    ):
        host._last_hourly_report = now
        report = (
            f"⏳ Прошло {elapsed / 3600.0:.1f}ч из — лимита этапа. "
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

    if (
        host._stage_start_ah == 0
        and stage_before in {host.STAGE_PREP, host.STAGE_COOLING}
    ):
        host._stage_start_ah = ah
        if "log_event" not in actions:
            actions["log_event"] = (
                f"START | Емкость: {host.ah_capacity}Ah | profile={host.battery_type}"
            )

    if stage_before == host.STAGE_PREP:
        prep_v, prep_i = host._prep_target(temp)
        if voltage < float(PREP_VOLTAGE_V.default):
            actions["set_voltage"] = prep_v
            actions["set_current"] = prep_i
            return actions

        actions["log_event_end"] = host._make_log_event_end(
            now,
            ah,
            voltage,
            current,
            temp,
            f"V≥{float(PREP_VOLTAGE_V.default):g}В ({voltage:.2f}В)",
        )
        host.current_stage = host.STAGE_MAIN
        host._clear_restored_targets()
        host.stage_start_time = now
        host._stage_start_ah = ah
        host._start_ah = ah
        host._reset_delta_and_blanking(now)
        main_v, main_i = host._main_target(temp)
        actions["set_voltage"] = main_v
        actions["set_current"] = main_i
        host._add_phase_limits(actions, main_v, main_i)
        actions["notify"] = (
            "<b>✅ Фаза завершена:</b> Подготовка\n"
            "<b>🚀 Переход к:</b> Main Charge"
        )
        actions["log_event"] = f"START | Емкость: {host.ah_capacity}Ah"
        return actions

    if stage_before == host.STAGE_COOLING:
        if temp > warning:
            return actions

        actions["log_event_end"] = host._make_log_event_end(
            now,
            ah,
            voltage,
            current,
            temp,
            f"T≤{warning:g}°C ({temp:.1f}°C)",
        )
        return_stage = host._cooling_from_stage or host.STAGE_MAIN
        host.current_stage = return_stage
        host._clear_restored_targets()
        host.stage_start_time = now
        host._stage_start_ah = ah

        target_v = host._cooling_target_v
        target_i = host._cooling_target_i
        host._cooling_from_stage = None

        actions["set_voltage"] = target_v
        actions["set_current"] = target_i
        host._add_phase_limits(actions, target_v, target_i)
        actions["turn_on"] = True
        host._blanking_until = now + float(STAGE_TRANSITION_BLANKING_S.default)
        msg = (
            "🌡 <b>АКБ ОСТЫЛА - ВОЗВРАТ К ЗАРЯДУ!</b>\n"
            f"Температура: {temp:.1f}°C (норма: ≤{warning:g}°C)\n"
            f"Возврат к этапу: {return_stage}"
        )
        actions["notify"] = msg
        actions["log_event"] = f"START | Емкость: {host.ah_capacity}Ah"
        host.notify(msg)
        return actions

    # DONE has no automatic transition here; IDLE already returned above.
    return actions


__all__ = ["run_authoritative_residual_scaffold"]
