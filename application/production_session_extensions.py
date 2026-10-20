"""Production-only session extensions applied to the single charge host.

These functions keep continuity and cooling pause mechanics in application
orchestration while storing all mutable session state on the existing host.
"""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping
import logging
import math
import time
from typing import Any, Dict, Optional

from runtime.charge.evidence.first_stage import FirstStageAssessment, FirstStageState
from cooling_runtime import CoolingAwareShadowRecoveryRuntime
from runtime.charge.strategy.main_variables import agm_tail_hold_seconds, standard_tail_hold_seconds
from runtime.charge.runtime.cooling_guard import validate_cooling_pause
from pb_domain import BatteryCondition, ChargeIntent
from application.production_target_policy import bound_target, recipe_envelope
from runtime.charge.strategy.mix_variables import mix_max_active_seconds

logger = logging.getLogger("rd6018.application.production_session_extensions")
RUNTIME_SIGNAL_RESTORE_MAX_AGE_S = 120.0

_AUTO_OPERATOR_REASON_ADDITIONS = {
    "main_tail_hold_complete_standard_mix": "Основной заряд завершён по хвосту; начинается штатный Mix.",
    "main_tail_hold_complete_diagnostic_no_hv": "Основной заряд завершён; Diagnostic не разрешает автоматический HV.",
    "persistent_main_plateau_diagnostic_no_hv": "Подтверждена устойчивая полка; Diagnostic остановлен для анализа без HV.",
    "main_timeout_ca_efb_v1_compatible_mix": "Достигнут 72-часовой fallback Main; Ca/EFB продолжает штатным Mix.",
    "agm_main_timeout_low_current_cv_mix": "AGM достиг 72-часового fallback уже в CV с I≤0.2 A; разрешён финальный Mix.",
    "agm_main_timeout_without_low_current_tail": "AGM достиг 72 часов без безопасного низкотокового хвоста; требуется диагностика.",
    "agm_recovery_budget_exhausted_wait_for_tail": "AGM исчерпал сервисные recovery-попытки; остаёмся в Main и ждём нормальный хвост.",
}


def auto_operator_reason_text(host: Any) -> Dict[str, str]:
    return AUTO_OPERATOR_REASON_TEXT if hasattr(host, "_v2_cooling_pause") else OPERATOR_REASON_TEXT


def auto_stage_max_hours(host: Any, fallback: Optional[float]) -> Optional[float]:
    if (hasattr(host, "_v2_cooling_pause") and host.current_stage == host.STAGE_MIX
            and host.finish_timer_start is None):
        return mix_max_active_seconds(host.battery_type) / 3600.0
    return fallback


def auto_mix_elapsed_s(host: Any, now: float) -> float:
    authority = getattr(host, "_mix_active_authority", None)
    snapshot = getattr(authority, "snapshot", None)
    if snapshot is not None:
        try:
            if str(snapshot.session_id) == str(host.recovery_trace_context["session_id"]):
                return max(0.0, float(snapshot.elapsed_s))
        except Exception:
            pass
    return max(0.0, float(now) - float(host.stage_start_time))


def auto_session_rules_summary(host: Any, fallback: str) -> str:
    if not hasattr(host, "_v2_cooling_pause"):
        return fallback
    rules = {
        host.PROFILE_CA: "Main 14.7V; recovery budget 3/session; Mix max 20h active; normal finish -> SafeWait 2h.",
        host.PROFILE_EFB: "Main 14.8V; recovery budget 3/session; Mix max 24h active; normal finish -> SafeWait 2h.",
        host.PROFILE_AGM: "Main 14.4/14.6/14.8/15.0V; recovery budget 4/session; Mix max 10h active; normal finish -> SafeWait 2h.",
    }
    return rules.get(host.battery_type, fallback)


def auto_timers(host: Any, timers: Dict[str, Any]) -> Dict[str, Any]:
    if (not hasattr(host, "_v2_cooling_pause") or host.current_stage != host.STAGE_MIX
            or host.finish_timer_start is not None):
        return timers
    now = time.time()
    limit_s = mix_max_active_seconds(host.battery_type)
    elapsed = auto_mix_elapsed_s(host, now)
    remaining = max(0.0, limit_s - elapsed)
    timers["stage_limit_sec"] = limit_s
    timers["stage_elapsed_sec"] = elapsed
    timers["remaining_time"] = (f"{int(remaining // 3600):02d}:{int((remaining % 3600) // 60):02d}" if remaining > 0 else "00:00")
    return timers


def auto_ai_stage_snapshot(host: Any, snapshot: Dict[str, Any], temp_c: Optional[float] = None) -> Dict[str, Any]:
    if not hasattr(host, "_v2_cooling_pause"):
        return snapshot
    if host.current_stage == host.STAGE_MIX and host.finish_timer_start is None:
        snapshot["mix_active_elapsed_s"] = auto_mix_elapsed_s(host, time.time())
        snapshot["mix_timeout_semantics"] = "MIX_TIMEOUT -> Output OFF -> manual diagnosis"
        if host.battery_type == host.PROFILE_EFB:
            snapshot["summary"] = "Mix 16.5V / 0.03C: normal exit by ΔV/ΔI; 24h active-time authority ceiling."
            snapshot["transition"] = ("Normal exit by ΔV/ΔI; without delta, 24h active-time ceiling -> "
                                      "MIX_TIMEOUT, Output OFF, manual diagnosis.")
            policy = snapshot.get("mix_exit_policy")
            if isinstance(policy, dict):
                policy["fallback_limit_hours"] = 24.0
                policy["fallback_outcome"] = "MIX_TIMEOUT"
    return snapshot


def initialize_production_session_state(host: Any) -> None:
    """Initialize production extension fields on the existing charge host."""
    host._v2_continuous_tail_since = None
    host._v2_continuous_tail_stage_start = None
    host._v2_cooling_pause = None
    host._finish_evidence = None
    from mix_active_authority import initialize_mix_active_authority
    initialize_mix_active_authority(host)


def restore_production_session_state(
    host: Any,
    document: Dict[str, Any],
    *,
    output_is_on: Optional[Any],
    is_cv: Optional[bool],
    is_cc: Optional[bool],
) -> Optional[str]:
    """Restore non-Guard production extensions after canonical Guard read."""
    reset_continuous_tail_hold(host)
    if not document.get("v2_intent"):
        host._v2_intent = ChargeIntent.NORMAL
        host._v2_condition_before = BatteryCondition.UNKNOWN
        host._initialize_shadow_session(started_at=host._v2_trace_started_at)

    if host.current_stage == host.STAGE_MIX:
        restore_finish_state(host, document)
        restore_runtime_signal_state(
            host, document, output_is_on=output_is_on, is_cv=is_cv, is_cc=is_cc,
        )

    if host._restored_target_v > 0 and host._restored_target_i > 0:
        bounded_v, bounded_i = bound_target(
            (host._restored_target_v, host._restored_target_i),
            recipe_envelope(
                profile=host.battery_type,
                capacity_ah=host.ah_capacity,
                battery_id=host._v2_battery_id,
                intent=host._v2_intent,
                condition=host._v2_condition_before,
            ),
            hv=host.current_stage in {host.STAGE_DESULFATION, host.STAGE_MIX},
        )
        host._restored_target_v = bounded_v
        host._restored_target_i = bounded_i

    pause = document.get("v2_cooling_pause")
    if host.current_stage == host.STAGE_COOLING and isinstance(pause, dict):
        host._v2_cooling_pause = dict(pause)
        host._cooling_from_stage = str(pause.get("source_stage") or host.STAGE_MAIN)
        host._cooling_target_v = float(pause.get("target_v") or 0.0)
        host._cooling_target_i = float(pause.get("target_i") or 0.0)
        host.finish_timer_start = pause.get("finish_timer_start")
        host._delta_reported = bool(pause.get("delta_reported", False))
        host._delta_trigger_mode = pause.get("delta_trigger_mode")
        evidence = pause.get("finish_evidence")
        host._finish_evidence = (
            dict(evidence)
            if valid_finish_evidence(host, evidence, mode=host._delta_trigger_mode)
            else None
        )
        restore_runtime_signal_snapshot(host, dict(pause.get("runtime_signal") or {}))
        host._v2_target_voltage_v = host._cooling_target_v or host._v2_target_voltage_v

    if host.current_stage == host.STAGE_COOLING:
        valid, reason = validate_cooling_pause(host, host._v2_cooling_pause)
        if not valid:
            host.stop(clear_session=True)
            return (
                "Cooling session rejected: durable V2 pause state is missing/invalid "
                f"({reason}); automatic resume is disabled and Output must remain OFF."
            )
    from mix_active_authority import restore_mix_active_authority
    rejection = restore_mix_active_authority(host)
    if rejection is not None:
        return rejection
    return None


def reset_continuous_tail_hold(host: Any) -> None:
    host._v2_continuous_tail_since = None
    host._v2_continuous_tail_stage_start = None


def apply_continuous_tail_hold(
    host: Any,
    assessment: Optional[FirstStageAssessment],
    *,
    stage_before: str,
    timestamp_s: float,
) -> Optional[FirstStageAssessment]:
    """Apply uninterrupted MAIN tail residence without owning another state graph."""
    if not hasattr(host, "_v2_continuous_tail_since"):
        return assessment
    if stage_before != host.STAGE_MAIN or assessment is None:
        reset_continuous_tail_hold(host)
        return assessment

    timestamp_s = float(timestamp_s)
    stage_marker = float(host.stage_start_time or 0.0)
    if host._v2_continuous_tail_stage_start != stage_marker:
        host._v2_continuous_tail_stage_start = stage_marker
        host._v2_continuous_tail_since = None
    if assessment.state != FirstStageState.TAIL_READY:
        host._v2_continuous_tail_since = None
        return assessment
    if host._v2_continuous_tail_since is None:
        host._v2_continuous_tail_since = timestamp_s
    held_s = max(0.0, timestamp_s - host._v2_continuous_tail_since)
    required_s = (
        agm_tail_hold_seconds()
        if host.battery_type == host.PROFILE_AGM
        else standard_tail_hold_seconds()
    )
    if held_s + 1e-6 >= required_s:
        return assessment
    return replace(
        assessment,
        state=FirstStageState.BULK_OR_TAPER,
        reason=f"continuous tail hold {held_s / 3600.0:.2f}h / {required_s / 3600.0:.2f}h",
    )


def capture_cooling_pause(
    host: Any,
    *,
    entered_at: float,
    source_stage: str,
    source_stage_start_time: float,
    source_stage_start_ah: float,
    source_target: tuple[float, float],
    source_finish_timer_start: Optional[float],
    source_first_hold_since: Optional[float],
    source_first_hold_current: Optional[float],
    source_cv_since: Optional[float],
    source_tail_since: Optional[float],
    source_runtime_signal: Dict[str, Any],
) -> None:
    host._v2_cooling_pause = {
        "source_stage": source_stage,
        "entered_at": float(entered_at),
        "source_stage_start_time": float(source_stage_start_time),
        "source_stage_start_ah": float(source_stage_start_ah),
        "target_v": float(source_target[0]),
        "target_i": float(source_target[1]),
        "finish_timer_start": source_finish_timer_start,
        "first_stage_hold_since": source_first_hold_since,
        "first_stage_hold_current": source_first_hold_current,
        "cv_since": source_cv_since,
        "continuous_tail_since": source_tail_since,
        "delta_reported": bool(host._delta_reported),
        "delta_trigger_mode": host._delta_trigger_mode,
        "finish_evidence": dict(host._finish_evidence) if host._finish_evidence else None,
        "runtime_signal": source_runtime_signal,
    }
    host._cooling_from_stage = source_stage
    host._cooling_target_v, host._cooling_target_i = source_target
    host.finish_timer_start = source_finish_timer_start
    host._stuck_current_since = None
    host._stuck_current_value = None
    host._main_sample_evidence.reset()
    host._delta_trigger_count = 0
    host._last_delta_confirm_time = 0.0


def resume_cooling_pause(host: Any, *, resumed_at: float) -> None:
    pause = host._v2_cooling_pause
    if not pause:
        return
    duration = max(0.0, float(resumed_at) - float(pause["entered_at"]))
    host.stage_start_time = float(pause["source_stage_start_time"]) + duration
    host._stage_start_ah = float(pause.get("source_stage_start_ah") or host._stage_start_ah)
    finish = pause.get("finish_timer_start")
    host.finish_timer_start = float(finish) + duration if finish is not None else None
    hold_since = pause.get("first_stage_hold_since")
    host._first_stage_hold_since = float(hold_since) + duration if hold_since is not None else None
    host._first_stage_hold_current = pause.get("first_stage_hold_current")
    cv_since = pause.get("cv_since")
    host._cv_since = float(cv_since) + duration if cv_since is not None else None
    tail_since = pause.get("continuous_tail_since")
    host._v2_continuous_tail_since = float(tail_since) + duration if tail_since is not None else None
    host._v2_continuous_tail_stage_start = host.stage_start_time
    host._stuck_current_since = None
    host._stuck_current_value = None
    host._main_sample_evidence.reset()
    host._delta_trigger_count = 0
    host._last_delta_confirm_time = 0.0
    host._delta_reported = bool(pause.get("delta_reported", False))
    host._delta_trigger_mode = pause.get("delta_trigger_mode")
    evidence = pause.get("finish_evidence")
    host._finish_evidence = dict(evidence) if isinstance(evidence, dict) else None
    runtime = host._v2_runtime
    if isinstance(runtime, CoolingAwareShadowRecoveryRuntime):
        restore_runtime_signal_snapshot(host, dict(pause.get("runtime_signal") or {}))
        runtime.resume_after_cooling(duration)
    host._v2_cooling_pause = None


def runtime_signal_snapshot(host: Any) -> Dict[str, Any]:
    runtime = host._v2_runtime
    if not isinstance(runtime, CoolingAwareShadowRecoveryRuntime):
        return {}
    tracker = runtime.tracker
    analyzer = tracker._analyzer
    return {
        "tracker_stage_key": tracker._stage_key,
        "tracker_stage_started_at": tracker._stage_started_at,
        "tracker_stage_start_ah": tracker._stage_start_ah,
        "analyzer_stage_name": analyzer.stage_name,
        "analyzer_target_voltage_v": analyzer.target_voltage_v,
        "current_min_a": analyzer._current_min_a,
        "current_min_time_s": analyzer._current_min_time_s,
        "voltage_max_v": analyzer._voltage_max_v,
        "voltage_max_time_s": analyzer._voltage_max_time_s,
        "reversal_confirmations": analyzer._reversal_confirmations,
        "last_reversal_confirmation_s": analyzer._last_reversal_confirmation_s,
        "reversal_emitted": analyzer._reversal_emitted,
        "voltage_reversal_confirmations": analyzer._voltage_reversal_confirmations,
        "last_voltage_reversal_confirmation_s": analyzer._last_voltage_reversal_confirmation_s,
        "voltage_reversal_emitted": analyzer._voltage_reversal_emitted,
    }


def restore_runtime_signal_snapshot(host: Any, state: Dict[str, Any]) -> None:
    runtime = host._v2_runtime
    if not isinstance(runtime, CoolingAwareShadowRecoveryRuntime) or not state:
        return
    tracker = runtime.tracker
    analyzer = tracker._analyzer
    tracker._stage_key = state.get("tracker_stage_key")
    tracker._stage_started_at = state.get("tracker_stage_started_at")
    tracker._stage_start_ah = state.get("tracker_stage_start_ah")
    analyzer.reset_stage(state.get("analyzer_stage_name"), target_voltage_v=state.get("analyzer_target_voltage_v"))
    analyzer._current_min_a = state.get("current_min_a")
    analyzer._current_min_time_s = state.get("current_min_time_s")
    analyzer._voltage_max_v = state.get("voltage_max_v")
    analyzer._voltage_max_time_s = state.get("voltage_max_time_s")
    analyzer._reversal_emitted = bool(state.get("reversal_emitted", False))
    analyzer._voltage_reversal_emitted = bool(state.get("voltage_reversal_emitted", False))
    analyzer._reversal_confirmations = int(state.get("reversal_confirmations", 0) or 0)
    analyzer._last_reversal_confirmation_s = state.get("last_reversal_confirmation_s")
    analyzer._voltage_reversal_confirmations = int(state.get("voltage_reversal_confirmations", 0) or 0)
    analyzer._last_voltage_reversal_confirmation_s = state.get("last_voltage_reversal_confirmation_s")




def session_document_extensions(host, document: Dict[str, Any]) -> Dict[str, Any]:
    """Return V2 continuation metadata for the canonical atomic session write."""
    result: Dict[str, Any] = {}
    if host._v2_cooling_pause is not None:
        result["v2_cooling_pause"] = host._v2_cooling_pause
    else:
        result.pop("v2_cooling_pause", None)

    context = host._v2_session_signal_context
    mode = context.get("mode") if isinstance(context, dict) else None
    runtime_valid = (
        host.current_stage == host.STAGE_MIX
        and isinstance(context, dict)
        and mode in {"CV", "CC"}
        and context.get("stage") == host.STAGE_MIX
        and context.get("session_id") == host._v2_trace_session_id
        and context.get("output_on") is True
        and context.get("telemetry_valid") is True
        and ((mode == "CV" and context.get("cv_state") is True and context.get("current_min_a") is not None)
             or (mode == "CC" and context.get("cc_state") is True and context.get("voltage_max_v") is not None))
    )
    if runtime_valid:
        result["runtime_signal"] = {"version": 2, **context}
    else:
        result.pop("runtime_signal", None)

    try:
        timer = float(host.finish_timer_start)
        timer_valid = math.isfinite(timer) and timer > 0.0
    except (TypeError, ValueError, OverflowError):
        timer_valid = False
    finish_valid = (
        host.current_stage == host.STAGE_MIX and timer_valid
        and host._delta_reported is True
        and host._delta_trigger_mode in {"CV", "CC"}
        and bool(host._v2_trace_session_id)
    )
    if finish_valid:
        result.update({
            "delta_state_version": 1,
            "delta_session_id": host._v2_trace_session_id,
            "delta_reported": True,
            "delta_trigger_mode": host._delta_trigger_mode,
        })
        evidence = host._finish_evidence
        if valid_finish_evidence(host, evidence, mode=host._delta_trigger_mode):
            result["finish_evidence"] = dict(evidence)
        else:
            result.pop("finish_evidence", None)
    else:
        for key in (
            "delta_state_version", "delta_session_id", "delta_reported",
            "delta_trigger_mode", "finish_evidence",
        ):
            result.pop(key, None)
    return result

def restore_finish_state(host, document: Dict[str, Any]) -> None:
    host._delta_reported = False
    host._delta_trigger_mode = None
    host._finish_evidence = None
    if host.current_stage != host.STAGE_MIX:
        return
    marker_present = any(
        key in document
        for key in ("delta_state_version", "delta_session_id", "delta_reported", "delta_trigger_mode")
    )
    if host.finish_timer_start is None:
        if marker_present:
            logger.info("SESSION_RESTORE_FINISH_STATE_RESET reason=missing_finish_timer")
        return
    try:
        finish_timer = float(host.finish_timer_start)
    except (TypeError, ValueError, OverflowError):
        host.finish_timer_start = None
        logger.warning("SESSION_RESTORE_FINISH_STATE_RESET reason=invalid_finish_timer")
        return
    if not math.isfinite(finish_timer) or finish_timer <= 0.0:
        host.finish_timer_start = None
        logger.warning("SESSION_RESTORE_FINISH_STATE_RESET reason=invalid_finish_timer")
        return
    try:
        marker_version = int(document.get("delta_state_version", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        marker_version = 0
    if (
        marker_version != 1
        or document.get("delta_session_id") != host._v2_trace_session_id
        or document.get("delta_reported") is not True
        or document.get("delta_trigger_mode") not in {"CV", "CC"}
    ):
        logger.info("SESSION_RESTORE_FINISH_STATE_RESET reason=missing_or_incompatible_marker")
        return
    host.finish_timer_start = finish_timer
    host._delta_reported = True
    host._delta_trigger_mode = str(document["delta_trigger_mode"])
    evidence = document.get("finish_evidence")
    if valid_finish_evidence(host, evidence, mode=host._delta_trigger_mode):
        host._finish_evidence = dict(evidence)
        logger.info(
            "SESSION_RESTORE_FINISH_EVIDENCE mode=%s reference=%s delta=%s accepted_at=%.3f",
            evidence["mode"], evidence["reference_value"], evidence["accepted_delta"], evidence["accepted_at"],
        )
    elif evidence is not None:
        logger.info("SESSION_RESTORE_FINISH_EVIDENCE_UNAVAILABLE reason=missing_or_incompatible_summary")
    logger.info(
        "SESSION_RESTORE_FINISH_STATE mode=%s started_at=%.3f session=%s",
        host._delta_trigger_mode,
        finish_timer,
        host._v2_trace_session_id or "-",
    )

def valid_finish_evidence(host, evidence: Any, *, mode: str) -> bool:
    if not isinstance(evidence, dict) or mode not in {"CV", "CC"}:
        return False
    if evidence.get("version") != 1 or evidence.get("mode") != mode:
        return False
    if evidence.get("session_id") != host._v2_trace_session_id:
        return False
    try:
        reference = float(evidence["reference_value"])
        accepted_delta = float(evidence["accepted_delta"])
        accepted_at = float(evidence["accepted_at"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return all(math.isfinite(value) for value in (reference, accepted_delta, accepted_at))

def restore_runtime_signal_state(
    host,
    document: Dict[str, Any],
    *,
    output_is_on: Optional[Any],
    is_cv: Optional[bool],
    is_cc: Optional[bool],
) -> None:
    runtime_signal = document.get("runtime_signal") if isinstance(document, dict) else None

    def reset(reason: str) -> None:
        logger.warning("SESSION_RESTORE_SIGNAL_RESET reason=%s", reason)

    if not isinstance(runtime_signal, dict):
        reset("missing_runtime_signal")
        return
    if int(runtime_signal.get("version", 0) or 0) != 2:
        reset("unsupported_runtime_signal_version")
        return
    if runtime_signal.get("session_id") != host._v2_trace_session_id:
        reset("session_identity_mismatch")
        return
    mode = str(runtime_signal.get("mode") or "").upper()
    if mode not in {"CV", "CC"}:
        reset("unsupported_signal_mode")
        return
    try:
        generation = float(runtime_signal.get("session_generation"))
        observed_at = float(runtime_signal.get("telemetry_observed_at"))
        stored_age = float(runtime_signal.get("telemetry_age_s"))
        current_min_raw = runtime_signal.get("current_min_a")
        min_age_raw = runtime_signal.get("current_min_time_s")
        delta_reference_raw = runtime_signal.get("delta_reference_a")
        current_min = float(current_min_raw) if current_min_raw is not None else None
        min_age = float(min_age_raw) if min_age_raw is not None else None
        delta_reference = float(delta_reference_raw) if delta_reference_raw is not None else None
        voltage_max_raw = runtime_signal.get("voltage_max_v")
        voltage_max_age_raw = runtime_signal.get("voltage_max_time_s")
        delta_reference_v_raw = runtime_signal.get("delta_reference_v")
        voltage_max = float(voltage_max_raw) if voltage_max_raw is not None else None
        voltage_max_age = float(voltage_max_age_raw) if voltage_max_age_raw is not None else None
        delta_reference_v = (
            float(delta_reference_v_raw) if delta_reference_v_raw is not None else None
        )
        reversal_confirmations = int(runtime_signal.get("reversal_confirmations", 0) or 0)
        voltage_reversal_confirmations = int(
            runtime_signal.get("voltage_reversal_confirmations", 0) or 0
        )
        voltage_last_reversal_confirmation_s = runtime_signal.get(
            "voltage_last_reversal_confirmation_s"
        )
        voltage_reversal_emitted = bool(
            runtime_signal.get("voltage_reversal_emitted", False)
        )
    except (TypeError, ValueError, OverflowError):
        reset("invalid_runtime_signal_numbers")
        return
    if not all(
        math.isfinite(value)
        for value in (
            generation, observed_at, stored_age,
            *(value for value in (voltage_max, voltage_max_age, delta_reference_v) if value is not None),
            *(value for value in (current_min, min_age, delta_reference) if value is not None),
        )
    ) or reversal_confirmations < 0 or voltage_reversal_confirmations < 0:
        reset("invalid_runtime_signal_numbers")
        return
    if abs(generation - float(host._v2_trace_started_at)) > 1e-6:
        reset("session_generation_mismatch")
        return
    age = max(0.0, time.time() - observed_at)
    if runtime_signal.get("output_on") is not True or output_is_on is not True:
        reset("output_not_confirmed_on")
        return
    if runtime_signal.get("telemetry_valid") is not True:
        reset("saved_evidence_not_valid")
        return
    observed_mode = "CV" if is_cv is True else ("CC" if is_cc is True else None)
    if observed_mode != mode:
        reset("mode_mismatch")
        return
    if age > RUNTIME_SIGNAL_RESTORE_MAX_AGE_S or stored_age > RUNTIME_SIGNAL_RESTORE_MAX_AGE_S:
        reset("telemetry_stale")
        return
    if mode == "CV" and (
        runtime_signal.get("cv_state") is not True
        or current_min is None
        or min_age is None
        or delta_reference is None
        or current_min < 0.0
        or min_age < 0.0
        or abs(delta_reference - current_min) > 1e-6
    ):
        reset("invalid_delta_reference")
        return
    if mode == "CC" and (
        runtime_signal.get("cc_state") is not True
        or voltage_max is None
        or voltage_max_age is None
        or delta_reference_v is None
        or voltage_max <= 0.0
        or voltage_max_age < 0.0
        or abs(delta_reference_v - voltage_max) > 1e-6
    ):
        reset("invalid_delta_reference")
        return
    if host._v2_runtime is None or not hasattr(host._v2_runtime, "tracker"):
        reset("runtime_unavailable")
        return
    if runtime_signal.get("stage") != host.STAGE_MIX:
        reset("stage_mismatch")
        return

    state = {
        "tracker_stage_key": host.STAGE_MIX.lower(),
        "tracker_stage_started_at": host._v2_runtime.tracker._stage_started_at,
        "tracker_stage_start_ah": host._v2_runtime.tracker._stage_start_ah,
        "analyzer_stage_name": host.STAGE_MIX.lower(),
        "analyzer_target_voltage_v": runtime_signal.get("target_voltage_v"),
        "current_min_a": current_min if mode == "CV" else None,
        "current_min_time_s": observed_at - min_age if mode == "CV" else None,
        "reversal_confirmations": reversal_confirmations if mode == "CV" else 0,
        "last_reversal_confirmation_s": (
            runtime_signal.get("last_reversal_confirmation_s") if mode == "CV" else None
        ),
        "reversal_emitted": bool(runtime_signal.get("reversal_emitted", False)) if mode == "CV" else False,
        "voltage_max_v": voltage_max if mode == "CC" else None,
        "voltage_max_time_s": observed_at - voltage_max_age if mode == "CC" else None,
        "voltage_reversal_confirmations": (
            voltage_reversal_confirmations if mode == "CC" else 0
        ),
        "last_voltage_reversal_confirmation_s": (
            voltage_last_reversal_confirmation_s if mode == "CC" else None
        ),
        "voltage_reversal_emitted": (
            voltage_reversal_emitted if mode == "CC" else False
        ),
    }
    restore_runtime_signal_snapshot(host, state)
    logger.info(
        "SESSION_RESTORE_SIGNAL_STATE mode=%s reference=%s age=%.1fs confirmations=%s session=%s",
        mode,
        f"{current_min:.3f}A" if mode == "CV" else f"{voltage_max:.3f}V",
        age,
        state["reversal_confirmations"],
        host._v2_trace_session_id or "-",
    )

OPERATOR_REASON_TEXT = {
    "main_tail_hold_complete_recovery_hv_authorized": "Хвост основного заряда стабилен; восстановительный HV-этап разрешён.",
    "main_tail_hold_complete_normal_charge": "Хвост основного заряда стабилен; основной заряд завершён.",
    "moderate_stable_cv_plateau_recovery_evidence": "Подтверждена стабильная CV-полка; разрешён сервисный этап восстановления.",
    "moderate_plateau_after_desulfation_budget": "CV-полка сохраняется после допустимых сервисных попыток; переход в Mix.",
    "agm_tail_hold_complete_advance_voltage_step": "AGM-хвост стабилен; переход на следующую ступень напряжения.",
    "persistent_main_plateau_requires_recovery_intent": "Устойчивая полка требует отдельного режима восстановления.",
    "confirmed_delta_finish_hold_complete": "Подтверждённая Delta выдержана 2 часа; активный этап завершён.",
    "mix_profile_observation_window_exhausted": "Достигнут максимальный безопасный интервал наблюдения Mix.",
    "mode_specific_end_of_charge_evidence_confirmed": "Подтверждён признак окончания заряда; запущена двухчасовая контрольная выдержка.",
}

AUTO_OPERATOR_REASON_TEXT = {**OPERATOR_REASON_TEXT, **_AUTO_OPERATOR_REASON_ADDITIONS}


def operatorize_notification(text: str, *, reasons: Mapping[str, str] | None = None) -> str:
    result = str(text or "")
    for reason, human in (reasons or OPERATOR_REASON_TEXT).items():
        result = result.replace(reason, human)
    replacements = {
        "<b>🚀 V2 → Mix Mode</b>": "<b>🚀 Переход в Mix</b>",
        "<b>🎯 V2 Delta подтверждена</b>": "<b>🎯 Delta подтверждена</b>",
        "<b>✅ V2: этап завершён.</b>": "<b>✅ Этап завершён.</b>",
        "<b>🛑 V2 остановил автоматическую эскалацию.</b>": "<b>🛑 Автоматический переход остановлен.</b>",
        "<b>🚀 V2 AGM ступень": "<b>🚀 AGM ступень",
        "🔧 <b>V2 десульфатация": "🔧 <b>Десульфатация",
        "Sticky finish-hold: 2ч.": "Контрольная выдержка: 2 ч.",
    }
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


__all__ = [
    "apply_continuous_tail_hold", "capture_cooling_pause", "operatorize_notification",
    "reset_continuous_tail_hold", "resume_cooling_pause", "restore_runtime_signal_snapshot",
    "runtime_signal_snapshot", "session_document_extensions", "restore_finish_state",
    "valid_finish_evidence", "restore_runtime_signal_state",
    "OPERATOR_REASON_TEXT",
]
