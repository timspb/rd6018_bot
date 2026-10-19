"""Pure assembly of stable charge trace and signal observation payloads."""

from __future__ import annotations

import math
import uuid
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from runtime.charge.evidence.first_stage import FirstStageAssessment
from runtime.charge.decisions import AuthorityDecision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryTraceContext:
    session_id: str
    started_at: float
    battery_id: str
    battery_type: str
    capacity_ah: float
    intent: Any
    condition_before: Any
    authoritative: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id, "started_at": self.started_at,
            "battery_id": self.battery_id, "battery_type": self.battery_type,
            "capacity_ah": self.capacity_ah, "intent": self.intent,
            "condition_before": self.condition_before,
            "authoritative": self.authoritative,
        }


def recovery_trace_context(host: object) -> RecoveryTraceContext:
    started_at = float(getattr(host, "_v2_trace_started_at", 0.0) or getattr(host, "total_start_time", 0.0) or 0.0)
    battery_type = getattr(host, "battery_type", "")
    capacity = getattr(host, "ah_capacity", 0.0)
    battery_id = getattr(host, "_v2_battery_id", None) or f"anonymous:{battery_type}:{capacity}"
    session_id = getattr(host, "_v2_trace_session_id", None)
    if not session_id:
        seed = f"{battery_id}|{battery_type}|{capacity}|{started_at:.6f}"
        session_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-volatile:{seed}").hex
    return RecoveryTraceContext(str(session_id), started_at, str(battery_id), str(battery_type),
                               float(capacity or 0.0), getattr(host, "_v2_intent", None),
                               getattr(host, "_v2_condition_before", None))


class TraceLifecycle:
    """Own throttled shadow diagnostics and delegate capture to persistence."""

    def __init__(self) -> None:
        self.last_disagreement: Optional[str] = None
        self.disagreement_repeat_count = 0

    def reset_disagreement(self) -> None:
        self.last_disagreement = None
        self.disagreement_repeat_count = 0

    def observe_disagreement(self, record: Any, *, stage: str) -> None:
        disagreement = record.disagreement
        if disagreement is None:
            self.last_disagreement = None
            self.disagreement_repeat_count = 0
            return
        if disagreement == self.last_disagreement:
            self.disagreement_repeat_count += 1
        else:
            self.last_disagreement = disagreement
            self.disagreement_repeat_count = 1
        if self.disagreement_repeat_count != 1 and self.disagreement_repeat_count % 20 != 0:
            return
        logger.warning(
            "RECOVERY_SHADOW disagreement=%s repeats=%d decision=%s legacy=%s stage=%s reason=%s",
            disagreement, self.disagreement_repeat_count, record.decision.decision.value,
            record.legacy_effect, stage, record.decision.reason,
        )

    async def capture_if_ready(self, context: RecoveryTraceContext, shadow: Dict[str, Any], *, idle_stage: str) -> bool:
        from recovery_trace_store import capture_shadow_trace_if_ready
        return await capture_shadow_trace_if_ready(context, shadow, idle_stage=idle_stage)


def finite_or_nan(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return math.nan
    return parsed if math.isfinite(parsed) else math.nan


def finite_or_none(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def normalize_output_on(value: Any) -> Optional[bool]:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if value is True or raw == "on":
        return True
    if value is False or raw == "off":
        return False
    return None


@dataclass(frozen=True)
class TracePointInput:
    timestamp_s: float
    stage_before: str
    stage_after: str
    target_before: Optional[float]
    voltage: Any
    current: Any
    temp_ext: Any
    is_cv: bool
    is_cc: Optional[bool]
    ah: Any
    output_is_on: Any


def build_trace_point_metadata(sample: TracePointInput) -> Dict[str, Any]:
    return {
        "timestamp_s": float(sample.timestamp_s),
        "stage": str(sample.stage_before),
        "legacy_stage_after": str(sample.stage_after),
        "voltage_v": finite_or_none(sample.voltage),
        "current_a": finite_or_none(sample.current),
        "temp_c": finite_or_none(sample.temp_ext),
        "is_cv": bool(sample.is_cv),
        "is_cc": bool(sample.is_cc) if sample.is_cc is not None else None,
        "target_voltage_v": finite_or_none(sample.target_before),
        "ah": finite_or_none(sample.ah),
        "output_on": normalize_output_on(sample.output_is_on),
    }


@dataclass(frozen=True)
class SignalContextInput:
    stage: str
    mode: Optional[str]
    session_id: Optional[str]
    session_generation: float
    output_is_on: Any
    is_cv: bool
    is_cc: bool
    telemetry_valid: bool
    timestamp_s: float
    now_s: float
    target_voltage_v: Optional[float]
    metrics: Any
    analyzer: Any = None


def build_signal_context(sample: SignalContextInput) -> Dict[str, Any]:
    metrics = sample.metrics
    analyzer = sample.analyzer
    return {
        "stage": str(sample.stage),
        "mode": sample.mode,
        "session_id": sample.session_id,
        "session_generation": float(sample.session_generation),
        "output_on": normalize_output_on(sample.output_is_on),
        "cv_state": bool(sample.is_cv),
        "cc_state": bool(sample.is_cc),
        "telemetry_valid": bool(sample.telemetry_valid),
        "telemetry_observed_at": float(sample.timestamp_s),
        "telemetry_age_s": max(0.0, float(sample.now_s) - float(sample.timestamp_s)),
        "target_voltage_v": sample.target_voltage_v,
        "current_min_a": metrics.current_min_a,
        "current_min_time_s": (
            float(sample.timestamp_s) - float(analyzer._current_min_time_s)
            if analyzer is not None and analyzer._current_min_time_s is not None else None
        ),
        "delta_reference_a": metrics.current_min_a,
        "voltage_max_v": metrics.voltage_max_v,
        "voltage_max_time_s": (
            float(sample.timestamp_s) - float(analyzer._voltage_max_time_s)
            if analyzer is not None and analyzer._voltage_max_time_s is not None else None
        ),
        "delta_reference_v": metrics.voltage_max_v,
        "reversal_threshold_a": metrics.reversal_threshold_a,
        "reversal_confirmations": metrics.reversal_confirmations,
        "last_reversal_confirmation_s": (
            analyzer._last_reversal_confirmation_s if analyzer is not None else None
        ),
        "reversal_emitted": bool(analyzer._reversal_emitted) if analyzer is not None else False,
        "voltage_reversal_confirmations": metrics.voltage_reversal_confirmations,
        "voltage_last_reversal_confirmation_s": (
            analyzer._last_voltage_reversal_confirmation_s if analyzer is not None else None
        ),
        "voltage_reversal_emitted": (
            bool(analyzer._voltage_reversal_emitted) if analyzer is not None else False
        ),
    }


def first_stage_metadata(assessment: FirstStageAssessment) -> Dict[str, Any]:
    return {
        "state": assessment.state.value,
        "current_c_rate": assessment.current_c_rate,
        "tail_threshold_a": assessment.tail_threshold_a,
        "tail_threshold_c": assessment.tail_threshold_c,
        "near_target": assessment.near_target,
        "reason": assessment.reason,
    }


def build_shadow_metadata(
    record: Any,
    *,
    trace_point: Dict[str, Any],
    first_stage: Optional[FirstStageAssessment] = None,
    authority_decision: Optional[AuthorityDecision] = None,
) -> Dict[str, Any]:
    metrics = record.analysis.metrics
    payload = {
        "status": "ok",
        "decision": record.decision.decision.value,
        "reason": record.decision.reason,
        "events": sorted(event.value for event in record.analysis.events),
        "disagreement": record.disagreement,
        "legacy_effect": record.legacy_effect,
        "authority": "modular",
        "trace_point": trace_point,
        "metrics": {
            "d_voltage_v_per_min": metrics.d_voltage_v_per_min,
            "d_current_a_per_min": metrics.d_current_a_per_min,
            "d_temp_c_per_min": metrics.d_temp_c_per_min,
            "current_min_a": metrics.current_min_a,
            "seconds_since_current_min": metrics.seconds_since_current_min,
            "delta_current_from_min_a": metrics.delta_current_from_min_a,
            "reversal_threshold_a": metrics.reversal_threshold_a,
            "reversal_confirmations": metrics.reversal_confirmations,
            "voltage_max_v": metrics.voltage_max_v,
            "seconds_since_voltage_max": metrics.seconds_since_voltage_max,
            "delta_voltage_from_max_v": metrics.delta_voltage_from_max_v,
            "voltage_reversal_threshold_v": metrics.voltage_reversal_threshold_v,
            "voltage_reversal_confirmations": metrics.voltage_reversal_confirmations,
        },
    }
    if first_stage is not None:
        payload["first_stage"] = first_stage_metadata(first_stage)
    if authority_decision is not None:
        payload["authority_decision"] = {
            "action": authority_decision.action.value,
            "reason": authority_decision.reason,
        }
    return payload
