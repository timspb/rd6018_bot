"""Read-only UI and SignalAnalyzer diagnostic projections.

These snapshots expose observed runtime state only; they do not own charge
authority, transitions, persistence, telemetry collection, or physical IO.
"""

from __future__ import annotations

from typing import Any, Dict

from signal_analyzer import SignalEvent


def ui_support_snapshot(host) -> Dict[str, Any]:
    """Compact mode-specific status for Telegram/UI without exposing raw internals."""
    metrics: Dict[str, Any] = {}
    decision = None
    reason = None
    events = []
    raw_finish_evidence = getattr(host, "_finish_evidence", None)
    finish_evidence = None
    if isinstance(raw_finish_evidence, dict):
        finish_evidence = {
            "mode": raw_finish_evidence.get("mode"),
            "reference_value": raw_finish_evidence.get("reference_value"),
            "accepted_delta": raw_finish_evidence.get("accepted_delta"),
            "accepted_at": raw_finish_evidence.get("accepted_at"),
            "available": True,
        }
    if host._v2_runtime is not None and host._v2_runtime.records:
        last = host._v2_runtime.records[-1]
        m = last.analysis.metrics
        current_min_started_at = None
        sample_timestamp = getattr(last.analysis.sample, "timestamp_s", None)
        seconds_since_current_min = m.seconds_since_current_min
        if sample_timestamp is not None and seconds_since_current_min is not None:
            current_min_started_at = float(sample_timestamp) - float(seconds_since_current_min)
        decision = last.decision.decision.value
        reason = last.decision.reason
        events = sorted(event.value for event in last.analysis.events)
        metrics = {
            "d_voltage_v_per_min": m.d_voltage_v_per_min,
            "d_current_a_per_min": m.d_current_a_per_min,
            "d_temp_c_per_min": m.d_temp_c_per_min,
            "current_min_a": m.current_min_a,
            "seconds_since_current_min": seconds_since_current_min,
            "main_stable_hold_s": getattr(m, "main_stable_hold_s", None),
            "main_stable_since_s": getattr(m, "main_stable_since_s", None),
            "main_stability_status": getattr(m, "main_stability_status", "not_applicable"),
            "current_min_started_at": current_min_started_at,
            "delta_current_from_min_a": m.delta_current_from_min_a,
            "reversal_threshold_a": m.reversal_threshold_a,
            "voltage_max_v": m.voltage_max_v,
            "seconds_since_voltage_max": m.seconds_since_voltage_max,
            "delta_voltage_from_max_v": m.delta_voltage_from_max_v,
            "voltage_reversal_threshold_v": m.voltage_reversal_threshold_v,
        }
    runtime_analysis_available = bool(
        host._v2_runtime is not None and host._v2_runtime.records
    )
    # A record alone is not proof that the current extrema decision is
    # usable.  Neutral/off and invalid samples are deliberately recorded
    # for diagnostics, but must not authorize an operator-facing extrema
    # claim after restore or an output transition.
    runtime_evidence_available = False
    context = host._v2_session_signal_context
    if runtime_analysis_available and isinstance(context, dict):
        expected_mode = "CV" if host.is_cv else ("CC" if host.is_cc else None)
        last = host._v2_runtime.records[-1]
        runtime_evidence_available = (
            context.get("mode") == expected_mode
            and context.get("output_on") is True
            and context.get("telemetry_valid") is True
            and not last.analysis.has(SignalEvent.TELEMETRY_INVALID)
        )
    return {
        "authoritative": True,
        "battery_id": host._v2_battery_id,
        "intent": host._v2_intent.value,
        "condition": host._v2_condition_before.value,
        "stage": host.current_stage,
        "is_cv": bool(host.is_cv),
        "is_cc": bool(host.is_cc),
        "finish_hold_started_at": host.finish_timer_start,
        "delta_reported": bool(getattr(host, "_delta_reported", False)),
        "finish_evidence": finish_evidence,
        "runtime_analysis_available": runtime_analysis_available,
        "runtime_evidence_available": runtime_evidence_available,
        "decision": decision,
        "reason": reason,
        "events": events,
        "metrics": metrics,
    }

def signal_analyzer_diagnostic_snapshot(host) -> Dict[str, Any]:
    """Return a read-only, non-authoritative analyzer diagnostic snapshot.

    This deliberately exposes observation state only.  It is not consumed by
    the controller, safety gates, persistence, or operator HMI decisions.
    """
    context = host._v2_session_signal_context
    runtime = host._v2_runtime
    analyzer = getattr(getattr(runtime, "tracker", None), "_analyzer", None)
    records = getattr(runtime, "records", None) if runtime is not None else None
    last_record = records[-1] if records else None
    if analyzer is None or not isinstance(context, dict):
        return {
            "available": False,
            "session_id": context.get("session_id") if isinstance(context, dict) else host._v2_trace_session_id,
            "mode": context.get("mode") if isinstance(context, dict) else None,
            "runtime_evidence_available": False,
            "cc": {"voltage_max_v": None, "voltage_max_time": None,
                   "delta_reference_v": None, "voltage_reversal_confirmations": 0,
                   "voltage_reversal_emitted": False},
            "cv": {"current_min_a": None, "current_min_time": None,
                   "delta_reference_a": None, "current_reversal_confirmations": 0,
                   "current_reversal_emitted": False},
            "last_sample": None,
        }

    point = last_record.point if last_record is not None else None
    invalid = bool(last_record and last_record.analysis.has(SignalEvent.TELEMETRY_INVALID))
    output_on = context.get("output_on")
    accepted = bool(last_record is not None and not invalid and output_on is not False)
    reject_reason = None
    if invalid:
        reject_reason = "telemetry_invalid"
    elif last_record is not None and output_on is False:
        reject_reason = "output_off_gate"
    elif last_record is None:
        reject_reason = "no_runtime_sample"

    last_sample = None
    if point is not None:
        last_sample = {
            "timestamp": point.timestamp_s,
            "voltage": point.voltage_v,
            "current": point.current_a,
            "is_cv": point.is_cv,
            "is_cc": point.is_cc,
            "output_on": output_on,
            "telemetry_valid": not invalid,
            "accepted": accepted,
            "reject_reason": reject_reason,
        }
    snapshot = ui_support_snapshot(host)
    return {
        "available": True,
        "session_id": context.get("session_id"),
        "mode": context.get("mode"),
        "runtime_evidence_available": bool(snapshot.get("runtime_evidence_available")),
        "cc": {
            "voltage_max_v": analyzer._voltage_max_v,
            "voltage_max_time": analyzer._voltage_max_time_s,
            "delta_reference_v": analyzer._voltage_max_v,
            "voltage_reversal_confirmations": analyzer._voltage_reversal_confirmations,
            "voltage_reversal_emitted": bool(analyzer._voltage_reversal_emitted),
        },
        "cv": {
            "current_min_a": analyzer._current_min_a,
            "current_min_time": analyzer._current_min_time_s,
            "delta_reference_a": analyzer._current_min_a,
            "current_reversal_confirmations": analyzer._reversal_confirmations,
            "current_reversal_emitted": bool(analyzer._reversal_emitted),
        },
        "last_sample": last_sample,
    }
