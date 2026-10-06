"""Canonical controller identity and mutable state bootstrap for V3 charge runtime.

This module owns stage/profile identifiers and the compatibility-shaped mutable
state still consumed by the modular charge runtime.  It intentionally contains
no transition decisions, persistence, hardware writes, or historical FSM calls.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Optional


STAGE_PREP = "Подготовка"
STAGE_MAIN = "Main Charge"
STAGE_DESULFATION = "Десульфатация"
STAGE_MIX = "Mix Mode"
STAGE_SAFE_WAIT = "Безопасное ожидание"
STAGE_COOLING = "🌡 Остывание"
STAGE_DONE = "Done"
STAGE_IDLE = "Idle"

PROFILE_CA = "Ca/Ca"
PROFILE_EFB = "EFB"
PROFILE_AGM = "AGM"
PROFILE_CUSTOM = "Custom"


def initialize_controller_state(
    host: Any,
    hass_client: Any,
    notify_cb: Optional[Callable[[str], Any]] = None,
) -> None:
    """Initialize the accepted controller state surface without legacy FSM ownership."""

    host.hass = hass_client
    host.notify = notify_cb or (lambda _: None)
    host.battery_type = host.PROFILE_CA
    host.ah_capacity = 60
    host.current_stage = host.STAGE_IDLE
    host.stage_start_time = 0.0
    host.antisulfate_count = 0
    host.v_max_recorded = None
    host.i_min_recorded = None
    host.finish_timer_start = None
    host._phantom_alerted = False
    host.temp_history = deque(maxlen=100)
    host._last_log_time = 0.0
    host._agm_stage_idx = 0
    host._delta_reported = False
    host.is_cv = False
    host.is_cc = False
    host._delta_trigger_mode = None
    host._stuck_current_since = None
    host._stuck_current_value = None
    host.last_update_time = 0.0
    host.emergency_hv_disconnect = False
    host._phase_current_limit = 0.0
    host._temp_warning_alerted = False
    host._cooling_from_stage = None
    host._cooling_target_v = 0.0
    host._cooling_target_i = 0.0
    host._pending_log_event = None
    host._start_ah = 0.0
    host._stage_start_ah = 0.0
    host._last_checkpoint_time = 0.0
    host._last_save_time = 0.0
    host._safe_wait_next_stage = None
    host._safe_wait_target_v = 0.0
    host._safe_wait_target_i = 0.0
    host._safe_wait_start = 0.0
    host._last_hourly_report = 0.0
    host._analytics_history = deque(maxlen=1000)
    host._safe_wait_v_samples = deque(maxlen=288)
    host._last_safe_wait_sample = 0.0
    host._blanking_until = 0.0
    host._delta_monitor_after = 0.0
    host._delta_trigger_count = 0
    host._session_start_reason = "User Command"
    host._last_known_output_on = False
    host._was_unavailable = False
    host._link_lost_at = 0.0
    host._link_loss_notice_count = 0
    host._link_loss_last_notice_at = 0.0
    host._restored_target_v = 0.0
    host._restored_target_i = 0.0
    host._device_set_voltage = None
    host._device_set_current = None
    host._temp_comp_last_update_time = 0.0
    host._temp_comp_last_temp = None
    host._stage_start_voltage = 0.0
    host._stage_start_current = 0.0
    host._stage_start_temp = 0.0
    host._last_voltage = 0.0
    host._last_current = 0.0
    host._last_temp_ext = 0.0
    host._last_ah = 0.0
    host._bank_fault_alerted = False
    host._bank_fault_last_score = 0
    host._bank_fault_last_status = "stable"
    host._bank_fault_last_reasons = []
    host._current_stage = host.STAGE_IDLE
    host._stage_tracking_enabled = False
    host.previous_stage = None
    host._last_transition_reason = ""
    host._stage_history = deque(maxlen=8)
    host.v_history = deque(maxlen=1440)
    host.i_history = deque(maxlen=1440)
    host._last_v_i_history_time = 0.0
    host._last_delta_confirm_time = 0.0
    host._cv_since = None
    host.total_start_time = 0.0
    host._first_stage_hold_since = None
    host._first_stage_hold_current = None
    host._custom_main_voltage = 14.7
    host._custom_main_current = 5.0
    host._custom_delta_threshold = 0.03
    host._custom_time_limit_hours = 24.0
    host._done_completion_kind = None
    host._done_output_intent = "off"
    host._done_outcome_authoritative = False
    host._done_transition_source_stage = None


__all__ = [
    "PROFILE_AGM",
    "PROFILE_CA",
    "PROFILE_CUSTOM",
    "PROFILE_EFB",
    "STAGE_COOLING",
    "STAGE_DESULFATION",
    "STAGE_DONE",
    "STAGE_IDLE",
    "STAGE_MAIN",
    "STAGE_MIX",
    "STAGE_PREP",
    "STAGE_SAFE_WAIT",
    "initialize_controller_state",
]


def mark_stage_sample(host: Any, voltage: float, current: float, temp: float, ah: float) -> None:
    host._last_voltage = float(voltage)
    host._last_current = float(current)
    host._last_temp_ext = float(temp)
    host._last_ah = float(ah)
    if host._stage_start_voltage <= 0.0:
        host._stage_start_voltage = float(voltage)
    if host._stage_start_current <= 0.0:
        host._stage_start_current = float(current)
    if host._stage_start_temp <= 0.0:
        host._stage_start_temp = float(temp)


def reset_stage_metrics(host: Any) -> None:
    host._stage_start_voltage = 0.0
    host._stage_start_current = 0.0
    host._stage_start_temp = 0.0
    host._last_voltage = 0.0
    host._last_current = 0.0
    host._last_temp_ext = 0.0
    host._last_ah = 0.0


def reset_bank_fault_state(host: Any) -> None:
    host._bank_fault_alerted = False
    host._bank_fault_last_score = 0
    host._bank_fault_last_status = "stable"
    host._bank_fault_last_reasons = []


def reset_link_loss_state(host: Any) -> None:
    host._link_loss_notice_count = 0
    host._link_loss_last_notice_at = 0.0


def clear_restored_targets(host: Any) -> None:
    host._restored_target_v = 0.0
    host._restored_target_i = 0.0


def reset_delta_and_blanking(host: Any, now: float, *, delay_s: float) -> None:
    host.v_max_recorded = None
    host.i_min_recorded = None
    host._delta_trigger_count = 0
    host._delta_trigger_mode = None
    host._first_stage_hold_since = None
    host._first_stage_hold_current = None
    host._stuck_current_since = None
    host._stuck_current_value = None
    host._blanking_until = float(now) + float(delay_s)
    host._delta_monitor_after = float(now) + float(delay_s)
