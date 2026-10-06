"""Lifecycle operations for the compatibility-shaped V3 charge controller."""

from __future__ import annotations

import logging
import time
from typing import Any

from charging_log import log_session_header
from runtime.charge.runtime.variables import DELTA_MONITOR_DELAY_S
from runtime.safety.variables import MAX_STAGE_CURRENT_A


logger = logging.getLogger("rd6018")


def reset_session_data(host: Any) -> None:
    logger.info("reset_session_data: clearing session history and counters")
    host._analytics_history.clear()
    host.v_history.clear()
    host.i_history.clear()
    host._safe_wait_v_samples.clear()
    host._start_ah = 0.0
    host._stage_start_ah = 0.0
    host._last_checkpoint_time = 0.0
    host._last_hourly_report = 0.0
    host._last_v_i_history_time = 0.0
    host._last_safe_wait_sample = 0.0
    host._stuck_current_since = None
    host._stuck_current_value = None
    host._first_stage_hold_since = None
    host._first_stage_hold_current = None
    host.previous_stage = None
    host._last_transition_reason = ""
    host._stage_history.clear()
    host._reset_stage_metrics()
    host._reset_bank_fault_state()
    host._reset_link_loss_state()
    host._stage_tracking_enabled = False


def initialize_session(host: Any, battery_type: str, ah_capacity: int, start_stage: str) -> None:
    host.reset_session_data()
    host.battery_type = battery_type
    host.ah_capacity = max(1, ah_capacity)
    host._stage_tracking_enabled = True
    host.current_stage = start_stage
    host.stage_start_time = time.time()
    host._stage_start_ah = 0.0
    host._reset_stage_metrics()
    host._reset_bank_fault_state()
    host.total_start_time = host.stage_start_time
    host.antisulfate_count = 0
    host.v_max_recorded = None
    host.i_min_recorded = None
    host.finish_timer_start = None
    host._phantom_alerted = False
    host.temp_history.clear()
    host._agm_stage_idx = 0
    host._delta_reported = False
    host._delta_trigger_mode = None
    host._stuck_current_since = None
    host._stuck_current_value = None
    host.emergency_hv_disconnect = False
    host._temp_warning_alerted = False
    host._cooling_from_stage = None
    host._cooling_target_v = 0.0
    host._cooling_target_i = 0.0
    host._pending_log_event = None
    host._safe_wait_next_stage = None
    host._safe_wait_target_v = 0.0
    host._safe_wait_target_i = 0.0
    host._safe_wait_start = 0.0
    host._blanking_until = 0.0
    host._delta_trigger_count = 0
    host._last_delta_confirm_time = 0.0
    host._cv_since = None
    host._first_stage_hold_since = None
    host._first_stage_hold_current = None
    host._session_start_reason = "User Command"
    host._temp_comp_last_update_time = 0.0
    host._temp_comp_last_temp = None
    host._reset_link_loss_state()
    host.previous_stage = None
    host._last_transition_reason = ""
    host._stage_history.clear()
    host._clear_restored_targets()
    host._clear_session_file()


def start_charge(host: Any, battery_type: str, ah_capacity: int) -> None:
    host._init_session(battery_type, ah_capacity, host.STAGE_PREP)
    target_v, target_i = host._get_target_v_i()
    log_session_header(
        "start",
        host.current_stage,
        0.0, 0.0, 0.0, 0.0,
        host.battery_type,
        host.ah_capacity,
        host._session_rules_summary(),
        meta={
            "session_reason": host._session_start_reason,
            "target_v": f"{target_v:.2f}",
            "target_i": f"{target_i:.2f}",
        },
    )
    logger.info(
        "ChargeController started: %s %dAh (%s)",
        battery_type,
        host.ah_capacity,
        host._session_start_reason,
    )


def start_custom_charge(
    host: Any,
    *,
    main_voltage: float,
    main_current: float,
    delta_threshold: float,
    time_limit_hours: float,
    ah_capacity: int,
) -> None:
    host._init_session(host.PROFILE_CUSTOM, ah_capacity, host.STAGE_MAIN)
    host._custom_main_voltage = main_voltage
    host._custom_main_current = min(float(MAX_STAGE_CURRENT_A.default), max(0.1, main_current))
    host._custom_delta_threshold = delta_threshold
    host._custom_time_limit_hours = max(1.0, time_limit_hours)
    delay = float(DELTA_MONITOR_DELAY_S.default)
    now = time.time()
    host._blanking_until = now + delay
    host._delta_monitor_after = now + delay
    host._session_start_reason = "Custom Mode"
    target_v, target_i = host._get_target_v_i()
    log_session_header(
        "start",
        host.current_stage,
        0.0, 0.0, 0.0, 0.0,
        host.battery_type,
        host.ah_capacity,
        host._session_rules_summary(),
        meta={
            "session_reason": host._session_start_reason,
            "target_v": f"{target_v:.2f}",
            "target_i": f"{target_i:.2f}",
            "delta_threshold": f"{host._custom_delta_threshold:.3f}",
            "time_limit_h": f"{host._custom_time_limit_hours:.1f}",
        },
    )
    logger.info(
        "ChargeController started CUSTOM: %.1fV/%.1fA delta=%.3fV limit=%.0fh capacity=%dAh",
        main_voltage,
        main_current,
        delta_threshold,
        time_limit_hours,
        ah_capacity,
    )


def stop_charge(host: Any, *, clear_session: bool = True) -> None:
    prev = host.current_stage
    if prev == host.STAGE_IDLE:
        return
    host.current_stage = host.STAGE_IDLE
    host._clear_restored_targets()
    host.v_max_recorded = None
    host.i_min_recorded = None
    if clear_session:
        host._clear_session_file()
    host._reset_stage_metrics()
    host._reset_bank_fault_state()
    logger.info("ChargeController stopped (was: %s)", prev)


def full_reset(host: Any) -> None:
    """Perform the accepted emergency/full controller-state reset."""

    host.stop()
    host.temp_history.clear()
    host._temp_warning_alerted = False
    host.finish_timer_start = None
    host._phantom_alerted = False
    host._delta_reported = False
    host._delta_trigger_mode = None
    host._stuck_current_since = None
    host._stuck_current_value = None
    host._safe_wait_next_stage = None
    host._analytics_history.clear()
    host._safe_wait_v_samples.clear()
    host.previous_stage = None
    host._last_transition_reason = ""
    host._stage_history.clear()
    host._reset_stage_metrics()
    host._reset_bank_fault_state()
    host._reset_link_loss_state()
    host._stage_tracking_enabled = False


__all__ = [
    "full_reset",
    "initialize_session",
    "reset_session_data",
    "start_charge",
    "start_custom_charge",
    "stop_charge",
]
