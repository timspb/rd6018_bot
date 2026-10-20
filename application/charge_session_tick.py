"""Application orchestration for one automatic charge-session tick.

Stage policy and physical execution remain in their existing domain owners.
This use case only sequences observation, evidence, authority, persistence, and
the resulting data-only action batch for the single active session.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, Optional

from application.recipe_policy import chemistry_for_profile
from application.charge_stage_tick import apply_charge_stage_authority, run_charge_stage_tick
from application.production_session_extensions import (
    apply_continuous_tail_hold,
    auto_operator_reason_text,
    capture_cooling_pause,
    operatorize_notification,
    resume_cooling_pause,
    runtime_signal_snapshot,
)
from mix_active_authority import MixActiveAuthorityError, mix_authority_session_id
from runtime.charge.diagnostics import refresh_stored_diagnostics
from runtime.charge.runtime.cooling_guard import finite, validate_cooling_pause
from recovery_session import RecoveryTracePoint
from runtime.charge.evidence.first_stage import FirstStageAssessment, MainSampleEvidenceInput
from runtime.charge.evidence.trace_context import (
    SignalContextInput,
    TracePointInput,
    build_shadow_metadata,
    build_signal_context,
    build_trace_point_metadata,
    finite_or_nan,
    log_analysis_events,
    normalize_output_on,
    recovery_trace_context as build_recovery_trace_context,
)
from runtime.charge.runtime.stop_diagnose import apply_stop_and_diagnose
from runtime.charge.strategy.main_variables import (
    AGM_PLATEAU_REQUIRED_MINUTES,
    PLATEAU_EVIDENCE_WINDOW_MINUTES,
    STANDARD_PLATEAU_REQUIRED_MINUTES,
)
from runtime.charge.runtime.stage_authority import is_authoritative_charge_stage
from signal_analyzer import SignalEvent


logger = logging.getLogger("rd6018.application.charge_tick")


async def refresh_pre_tick_diagnostics(host: Any) -> None:
    """Refresh stored diagnostic inputs before automatic decisions."""
    if hasattr(host, "_diagnostic_context"):
        await refresh_stored_diagnostics(host)


async def run_charge_session_tick(
    host: Any,
    voltage: float,
    current: float,
    temp_ext: Optional[float],
    is_cv: bool,
    ah: float,
    output_is_on: Optional[Any] = None,
    manual_off_active: bool = False,
    is_cc: Optional[bool] = None,
    manual_active: bool = False,
) -> Dict[str, Any]:
    """Run application tick plus production Cooling pause/resume orchestration."""
    authority_suspended = getattr(host, "_pb_background_suspended", None)
    if callable(authority_suspended) and authority_suspended():
        host.last_update_time = time.time()
        return {}
    production_cooling = hasattr(host, "_v2_cooling_pause")
    if production_cooling and host.is_active and host.battery_type != host.PROFILE_CUSTOM:
        host._last_hourly_report = time.time()

    stage_before = host.current_stage
    pause_before = (
        dict(host._v2_cooling_pause)
        if isinstance(getattr(host, "_v2_cooling_pause", None), dict)
        else None
    )
    if production_cooling and stage_before == host.STAGE_COOLING:
        valid, reason = validate_cooling_pause(host, pause_before)
        if not valid:
            return _fail_closed_cooling_actions(host, reason)

    safe_wait_start_before = None
    pre_target = (0.0, 0.0)
    pre_stage_start = pre_stage_start_ah = 0.0
    pre_finish = pre_hold_since = pre_hold_current = None
    pre_cv_since = pre_tail_since = None
    pre_runtime_signal: Dict[str, Any] = {}
    if production_cooling:
        safe_wait_start_before = (
            finite(getattr(host, "_safe_wait_start", None))
            if stage_before == host.STAGE_SAFE_WAIT
            else None
        )
        try:
            pre_target = tuple(float(value) for value in host._get_target_v_i(temp_ext))
        except Exception:
            pre_target = (
                float(getattr(host, "_cooling_target_v", None) or 0.0),
                float(getattr(host, "_cooling_target_i", None) or 0.0),
            )
        pre_stage_start = float(host.stage_start_time or 0.0)
        pre_stage_start_ah = float(host._stage_start_ah or 0.0)
        pre_finish = host.finish_timer_start
        pre_hold_since = host._first_stage_hold_since
        pre_hold_current = host._first_stage_hold_current
        pre_cv_since = host._cv_since
        pre_tail_since = host._v2_continuous_tail_since
        pre_runtime_signal = runtime_signal_snapshot(host)

    actions = await _run_charge_session_tick_body(
        host, voltage, current, temp_ext, is_cv, ah,
        output_is_on=output_is_on,
        manual_off_active=manual_off_active,
        is_cc=is_cc,
        manual_active=manual_active,
    )
    if not production_cooling:
        return actions

    now = float(host.last_update_time or time.time())
    if stage_before != host.STAGE_COOLING and host.current_stage == host.STAGE_COOLING:
        capture_cooling_pause(
            host,
            entered_at=now,
            source_stage=stage_before,
            source_stage_start_time=pre_stage_start,
            source_stage_start_ah=pre_stage_start_ah,
            source_target=pre_target,
            source_finish_timer_start=pre_finish,
            source_first_hold_since=pre_hold_since,
            source_first_hold_current=pre_hold_current,
            source_cv_since=pre_cv_since,
            source_tail_since=pre_tail_since,
            source_runtime_signal=pre_runtime_signal,
        )
        if stage_before == host.STAGE_SAFE_WAIT:
            if safe_wait_start_before is None or safe_wait_start_before <= 0:
                return _fail_closed_cooling_actions(host, "safe_wait_cooling_capture_failed")
            pause = dict(host._v2_cooling_pause or {})
            pause["source_safe_wait_start"] = float(safe_wait_start_before)
            host._v2_cooling_pause = pause
            valid, reason = validate_cooling_pause(host, pause)
            if not valid:
                return _fail_closed_cooling_actions(host, reason)
        host._save_session(float(voltage), float(current), float(ah))
    elif stage_before == host.STAGE_COOLING and host.current_stage != host.STAGE_COOLING:
        resume_cooling_pause(host, resumed_at=now)
        if host.current_stage == host.STAGE_SAFE_WAIT:
            assert pause_before is not None
            entered_at = float(pause_before["entered_at"])
            source_safe_wait_start = float(pause_before["source_safe_wait_start"])
            cooling_duration = max(0.0, float(now) - entered_at)
            host._safe_wait_start = source_safe_wait_start + cooling_duration
            for key in ("turn_on", "set_voltage", "set_current", "set_ovp", "set_ocp"):
                actions.pop(key, None)
            actions["turn_off"] = True
            actions["notify"] = (
                "🌡 АКБ остыла до порога возобновления. SAFE_WAIT продолжается с "
                "замороженным таймером; Output остаётся OFF."
            )
            actions["log_event"] = "COOLING -> SAFE_WAIT | OUTPUT_OFF_PRESERVED"
        host._save_session(float(voltage), float(current), float(ah))

    if isinstance(actions.get("notify"), str):
        actions["notify"] = operatorize_notification(
            actions["notify"],
            reasons=auto_operator_reason_text(host),
        )
    return actions


def _fail_closed_cooling_actions(host: Any, reason: str) -> Dict[str, Any]:
    try:
        host.stop(clear_session=True)
    except Exception:
        pass
    return {
        "emergency_stop": True,
        "turn_off": True,
        "log_event": f"V2_COOLING_FAIL_CLOSED | {reason}",
        "notify": (
            "🛑 <b>Cooling restore/resume заблокирован.</b> "
            f"Причина: <code>{reason}</code>. Output должен оставаться OFF; "
            "автоматическое продолжение сессии отменено."
        ),
    }


async def _run_charge_session_tick_body(
    host: Any,
    voltage: float,
    current: float,
    temp_ext: Optional[float],
    is_cv: bool,
    ah: float,
    output_is_on: Optional[Any] = None,
    manual_off_active: bool = False,
    is_cc: Optional[bool] = None,
    manual_active: bool = False,
) -> Dict[str, Any]:
    """Execute the shared non-Cooling automatic session orchestration."""
    stage_before = host.current_stage
    mix_authority = getattr(host, "_mix_active_authority", None)
    mix_session_id: Optional[str] = None
    if stage_before == host.STAGE_MIX and mix_authority is not None:
        mix_session_id = mix_authority_session_id(host)
        # Unknown Output cannot prove an inactive HV interval. Conservatively
        # charge it as active; runtime telemetry safety independently fails closed.
        output_state = normalize_output_on(output_is_on)
        mix_authority.observe(mix_session_id, active=(output_state is not False))

    await refresh_pre_tick_diagnostics(host)
    target_before = host._v2_target_voltage_v
    if target_before is None and stage_before not in {
        host.STAGE_IDLE, host.STAGE_SAFE_WAIT, host.STAGE_COOLING,
    }:
        try:
            target_before = float(host._get_target_v_i(temp_ext)[0])
        except Exception:
            target_before = None

    # Persistent Manual-OFF is an asynchronous terminal kill condition owned
    # outside AUTO chemistry. It cannot perturb automatic decisions in this tick.
    actions = await run_charge_stage_tick(
        host,
        stage_before=stage_before,
        voltage=voltage,
        current=current,
        temp_ext=temp_ext,
        is_cv=is_cv,
        ah=ah,
        output_is_on=output_is_on,
        manual_off_active=False,
        is_cc=is_cc,
        manual_active=manual_active,
    )

    timestamp_s = host.last_update_time or time.time()
    resolved_is_cc = bool(is_cc) if is_cc is not None else not bool(is_cv)
    authority_decision = None
    first_stage: Optional[FirstStageAssessment] = None
    try:
        runtime = host._v2_runtime
        if runtime is None:
            runtime = host._new_runtime(
                started_at=host._v2_trace_started_at or host.total_start_time or timestamp_s
            )
        record = runtime.observe(
            RecoveryTracePoint(
                timestamp_s=timestamp_s,
                stage=stage_before,
                voltage_v=finite_or_nan(voltage),
                current_a=finite_or_nan(current),
                temp_c=finite_or_nan(temp_ext),
                is_cv=bool(is_cv),
                is_cc=resolved_is_cc,
                target_voltage_v=target_before,
                ah=finite_or_nan(ah),
            ),
            legacy_actions=actions,
            output_is_on=normalize_output_on(output_is_on),
        )

        log_analysis_events(
            record,
            stage=stage_before,
            session_id=host._v2_trace_session_id,
            timestamp_s=timestamp_s,
        )
        metrics = record.analysis.metrics
        analyzer = getattr(getattr(runtime, "tracker", None), "_analyzer", None)
        mode = "CV" if bool(is_cv) else ("CC" if bool(resolved_is_cc) else None)
        host._v2_session_signal_context = build_signal_context(SignalContextInput(
            stage=stage_before,
            mode=mode,
            session_id=host._v2_trace_session_id,
            session_generation=float(host._v2_trace_started_at or 0.0),
            output_is_on=output_is_on,
            is_cv=bool(is_cv),
            is_cc=bool(resolved_is_cc),
            telemetry_valid=not record.analysis.has(SignalEvent.TELEMETRY_INVALID),
            timestamp_s=float(timestamp_s),
            now_s=time.time(),
            target_voltage_v=target_before,
            metrics=metrics,
            analyzer=analyzer,
        ))

        sample = MainSampleEvidenceInput(
            stage=stage_before,
            main_stage=host.STAGE_MAIN,
            target_voltage_v=target_before,
            timestamp_s=float(timestamp_s),
            voltage_v=float(voltage),
            current_a=float(current),
            is_cv=bool(is_cv),
            chemistry=chemistry_for_profile(host.battery_type),
            capacity_ah=float(host.ah_capacity),
            plateau_required_minutes=(
                float(AGM_PLATEAU_REQUIRED_MINUTES.default)
                if host.battery_type == host.PROFILE_AGM
                else float(STANDARD_PLATEAU_REQUIRED_MINUTES.default)
            ),
            plateau_window_minutes=float(PLATEAU_EVIDENCE_WINDOW_MINUTES.default),
            events=frozenset(record.analysis.events),
            dtemp_c_per_min=metrics.d_temp_c_per_min,
            dcurrent_a_per_min=metrics.d_current_a_per_min,
            dvoltage_v_per_min=metrics.d_voltage_v_per_min,
            temperature_c=getattr(getattr(record.analysis, "sample", None), "temp_c", None),
        )
        first_stage_evidence = host._main_sample_evidence.assess(sample)
        first_stage = apply_continuous_tail_hold(
            host,
            first_stage_evidence.assessment,
            stage_before=stage_before,
            timestamp_s=float(timestamp_s),
        )

        if is_authoritative_charge_stage(host, stage_before):
            temp_value = math.nan if temp_ext is None else finite_or_nan(temp_ext)
            if math.isfinite(temp_value):
                authority_decision = apply_charge_stage_authority(
                    host,
                    record=record,
                    first_stage=first_stage,
                    stage_before=stage_before,
                    timestamp_s=timestamp_s,
                    voltage=float(voltage),
                    current=float(current),
                    temp=temp_value,
                    ah=float(ah),
                    is_cv=bool(is_cv),
                    is_cc=resolved_is_cc,
                    actions=actions,
                    output_is_on=output_is_on,
                )
        else:
            host._trace_lifecycle.observe_disagreement(record, stage=stage_before)

        trace_point = build_trace_point_metadata(TracePointInput(
            timestamp_s=timestamp_s,
            stage_before=stage_before,
            stage_after=host.current_stage,
            target_before=target_before,
            voltage=voltage,
            current=current,
            temp_ext=temp_ext,
            is_cv=is_cv,
            is_cc=resolved_is_cc,
            ah=ah,
            output_is_on=output_is_on,
        ))
        actions["recovery_shadow"] = build_shadow_metadata(
            record,
            trace_point=trace_point,
            first_stage=first_stage,
            authority_decision=authority_decision,
        )
    except Exception as exc:
        logger.exception("Recovery observation/authority failed")
        host._v2_session_signal_context = None
        trace_point = build_trace_point_metadata(TracePointInput(
            timestamp_s=timestamp_s,
            stage_before=stage_before,
            stage_after=host.current_stage,
            target_before=target_before,
            voltage=voltage,
            current=current,
            temp_ext=temp_ext,
            is_cv=is_cv,
            is_cc=resolved_is_cc,
            ah=ah,
            output_is_on=output_is_on,
        ))
        actions["recovery_shadow"] = {
            "status": "error",
            "decision": None,
            "reason": "V2 observation/authority failed",
            "error_type": type(exc).__name__,
            "authority": "modular",
            "trace_point": trace_point,
        }
        if is_authoritative_charge_stage(host, stage_before) and host.current_stage == stage_before:
            temp_value = finite_or_nan(temp_ext)
            if math.isfinite(temp_value):
                apply_stop_and_diagnose(
                    host,
                    actions=actions,
                    now=timestamp_s,
                    voltage=finite_or_nan(voltage),
                    current=finite_or_nan(current),
                    temp=temp_value,
                    ah=finite_or_nan(ah),
                    reason=f"v2_internal_error:{type(exc).__name__}",
                )
            else:
                actions["emergency_stop"] = True
                actions["turn_off"] = True

    try:
        if await host._trace_lifecycle.capture_if_ready(
            build_recovery_trace_context(host), actions["recovery_shadow"],
            idle_stage=host.STAGE_IDLE,
        ):
            actions["recovery_shadow"]["persistence"] = "stored"
    except Exception as exc:
        logger.exception("RECOVERY_TRACE persistence failed; actuator decision remains valid")
        actions["recovery_shadow"]["persistence"] = "error"
        actions["recovery_shadow"]["persistence_error_type"] = type(exc).__name__

    next_target = actions.get("set_voltage")
    if next_target is not None:
        host._v2_target_voltage_v = finite_or_nan(next_target)
    elif host.current_stage != stage_before:
        try:
            host._v2_target_voltage_v = float(host._get_target_v_i(temp_ext)[0])
        except Exception:
            host._v2_target_voltage_v = None
    host._v2_last_stage = host.current_stage

    transition_reason = str(authority_decision.reason or "") if authority_decision is not None else ""
    if not transition_reason:
        transition_reason = str(actions.get("log_event") or actions.get("log_event_end") or "")
    host._log_stage_transition(
        old_stage=stage_before,
        new_stage=host.current_stage,
        timestamp_s=timestamp_s,
        reason=transition_reason,
    )
    if host.current_stage not in {host.STAGE_IDLE, host.STAGE_DONE}:
        host._save_session(float(voltage), float(current), float(ah))

    if mix_session_id is not None and host.current_stage != host.STAGE_MIX:
        try:
            mix_authority.set_inactive(mix_session_id)
        except MixActiveAuthorityError:
            pass
    elif (
        mix_authority is not None
        and stage_before != host.STAGE_MIX
        and host.current_stage == host.STAGE_MIX
    ):
        # A transition keeps/turns Output ON. Start now; conservative slight
        # over-count is preferable to extending automatic high-voltage authority.
        mix_session_id = mix_authority_session_id(host)
        try:
            mix_authority.observe(mix_session_id, active=True)
        except MixActiveAuthorityError:
            mix_authority.begin(mix_session_id, active=True)
    return actions


__all__ = ["run_charge_session_tick"]
