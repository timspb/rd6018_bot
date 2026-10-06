"""Runtime mechanics for authoritative MIX and final SAFE_WAIT.

This adapter preserves accepted common safety/bookkeeping behavior without
entering the historical ChargeController.tick(). MIX/final completion decisions
remain in modular strategy owners.
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


logger = logging.getLogger("rd6018.charge.mix_runtime")


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


async def run_authoritative_mix_scaffold(
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
    report_limit_s: float,
    now_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Run common safety/bookkeeping without historical stage transitions."""

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

    if temp >= pause:
        actions["log_event_end"] = host._make_log_event_end(
            now,
            ah,
            voltage,
            current,
            temp,
            f"T≥{pause:g}°C ({temp:.1f}°C)",
        )
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

    host._analytics_history.append((now, voltage, current, ah, temp))
    if now - host._last_v_i_history_time >= float(HISTORY_SAMPLE_INTERVAL_S.default):
        host.v_history.append((now, voltage))
        host.i_history.append((now, current))
        host._last_v_i_history_time = now

    elapsed_check = now - host.stage_start_time
    if elapsed_check < 0 or elapsed_check > float(STAGE_CLOCK_SANITY_MAX_HOURS.default) * 3600.0:
        host.stage_start_time = now
        elapsed_check = 0.0
        logger.warning("mix runtime: stage_start_time corrected (elapsed invalid)")

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

    if host._pending_log_event:
        actions["log_event"] = host._pending_log_event
        host._pending_log_event = None

    elapsed = max(0.0, now - host.stage_start_time)
    if now - host._last_log_time >= float(HISTORY_SAMPLE_INTERVAL_S.default):
        _phase_log(host.current_stage, voltage, current, temp)
        host._last_log_time = now

    if not manual_off_active and now - host._last_hourly_report >= float(
        OPERATOR_REPORT_INTERVAL_S.default
    ):
        host._last_hourly_report = now
        max_seconds = max(0.0, float(report_limit_s))
        report = (
            f"⏳ Прошло {elapsed / 3600.0:.1f}ч из {max_seconds / 3600.0:.0f} лимита этапа. "
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


__all__ = ["run_authoritative_mix_scaffold"]
