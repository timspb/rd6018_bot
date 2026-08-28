from __future__ import annotations

import json
import statistics
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional

from database import get_db
from recovery_session import HV_STAGE_NAMES, MAIN_STAGE_NAMES
from recovery_trace_store import TRACE_TABLE, init_recovery_trace_store


MIX_STAGE_NAMES = frozenset({"mix", "mix mode"})
TERMINAL_MIX_EXIT_NAMES = frozenset(
    {
        "safe wait",
        "safe_wait",
        "безопасное ожидание",
        "rest",
        "done",
        "storage",
        "хранение",
        "idle",
    }
)


def _normalize_stage(stage: Any) -> str:
    return " ".join(str(stage or "").strip().lower().replace("_", " ").split())


def _stage_kind(stage: Any) -> str:
    key = _normalize_stage(stage)
    if key in MAIN_STAGE_NAMES:
        return "main"
    if key in HV_STAGE_NAMES:
        return "hv"
    return "other"


def _is_terminal_mix_exit(stage_after: Any) -> bool:
    return _normalize_stage(stage_after) in TERMINAL_MIX_EXIT_NAMES


def _load_shadow_json(raw: Any) -> Mapping[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _finite_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _reversal_metrics(
    row: Any,
    shadow: Mapping[str, Any],
) -> Dict[str, Any]:
    metrics = shadow.get("metrics")
    if not isinstance(metrics, Mapping):
        metrics = {}
    imin_a = _finite_float(metrics.get("current_min_a"))
    delta_a = _finite_float(metrics.get("delta_current_from_min_a"))
    threshold_a = _finite_float(metrics.get("reversal_threshold_a"))
    threshold_source_raw = str(metrics.get("reversal_threshold_source") or "").strip()
    threshold_source = threshold_source_raw or None
    capacity_ah = _finite_float(row["capacity_ah"])

    imin_c_rate = (
        imin_a / capacity_ah
        if imin_a is not None and capacity_ah is not None and capacity_ah > 0
        else None
    )
    delta_c_rate = (
        delta_a / capacity_ah
        if delta_a is not None and capacity_ah is not None and capacity_ah > 0
        else None
    )
    threshold_c_rate = (
        threshold_a / capacity_ah
        if threshold_a is not None and capacity_ah is not None and capacity_ah > 0
        else None
    )
    delta_over_imin = (
        delta_a / imin_a
        if delta_a is not None and imin_a is not None and imin_a > 0
        else None
    )
    threshold_over_imin = (
        threshold_a / imin_a
        if threshold_a is not None and imin_a is not None and imin_a > 0
        else None
    )
    return {
        "current_min_a": imin_a,
        "current_min_c_rate": imin_c_rate,
        "reversal_delta_a": delta_a,
        "reversal_delta_c_rate": delta_c_rate,
        "reversal_delta_over_imin": delta_over_imin,
        "reversal_threshold_a": threshold_a,
        "reversal_threshold_c_rate": threshold_c_rate,
        "reversal_threshold_over_imin": threshold_over_imin,
        "reversal_threshold_source": threshold_source,
    }


def _sample_summary(row: Any, shadow: Mapping[str, Any]) -> Dict[str, Any]:
    first_stage = shadow.get("first_stage")
    if not isinstance(first_stage, Mapping):
        first_stage = {}
    audit = shadow.get("transition_audit")
    if not isinstance(audit, Mapping):
        audit = {}
    return {
        "timestamp_s": float(row["timestamp_s"]),
        "stage": row["stage"],
        "legacy_stage_after": row["legacy_stage_after"],
        "voltage_v": row["voltage_v"],
        "current_a": row["current_a"],
        "temp_c": row["temp_c"],
        "current_c_rate": first_stage.get("current_c_rate"),
        "first_stage_state": first_stage.get("state"),
        "shadow_status": row["shadow_status"],
        "shadow_decision": row["shadow_decision"],
        "disagreement": row["disagreement"],
        "transition_audit_code": row["transition_audit_code"],
        "transition_audit_severity": row["transition_audit_severity"],
        "reversal": _reversal_metrics(row, shadow),
        "reason": audit.get("reason") or row["shadow_reason"],
    }


def _distribution(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"min": None, "median": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def _render_stage_reversal(values: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    rendered: Dict[str, Any] = {}
    for stage, bucket in values.items():
        timestamps = list(bucket.get("timestamps") or [])
        rendered[stage] = {
            "confirmed_count": len(timestamps),
            "first_confirmed_at": timestamps[0] if timestamps else None,
            "reversal_delta_a": _distribution(list(bucket.get("delta_a") or [])),
            "reversal_delta_c_rate": _distribution(list(bucket.get("delta_c_rate") or [])),
            "reversal_delta_over_imin": _distribution(list(bucket.get("delta_over_imin") or [])),
            "reversal_threshold_a": _distribution(list(bucket.get("threshold_a") or [])),
            "reversal_threshold_c_rate": _distribution(list(bucket.get("threshold_c_rate") or [])),
            "reversal_threshold_over_imin": _distribution(list(bucket.get("threshold_over_imin") or [])),
            "threshold_source": dict(bucket.get("threshold_source") or {}),
            "current_min_c_rate": _distribution(list(bucket.get("imin_c_rate") or [])),
        }
    return rendered


async def build_trace_report(
    session_id: str,
    *,
    max_calibration_samples: int = 30,
) -> Dict[str, Any]:
    """Summarize one captured live session for legacy↔V2 calibration.

    The report deliberately reports observations and timing. It does not convert a
    disagreement into an actuator command or a battery health score.
    """
    await init_recovery_trace_store()
    db = await get_db()
    async with db.execute(
        f"SELECT * FROM {TRACE_TABLE} WHERE session_id = ? ORDER BY timestamp_s ASC, id ASC",
        (str(session_id),),
    ) as cursor:
        rows = await cursor.fetchall()
    if not rows:
        raise KeyError(f"unknown trace session: {session_id}")

    decisions: Counter[str] = Counter()
    disagreements: Counter[str] = Counter()
    first_stage_states: Counter[str] = Counter()
    audit_codes: Counter[str] = Counter()
    audit_severities: Counter[str] = Counter()
    legacy_transitions: Counter[str] = Counter()
    terminal_mix_transitions: Counter[str] = Counter()
    interrupted_mix_transitions: Counter[str] = Counter()
    threshold_sources: Counter[str] = Counter()

    shadow_errors = 0
    calibration_samples: List[Dict[str, Any]] = []
    first_v2_finish_at: Optional[float] = None
    first_v2_mix_finish_at: Optional[float] = None
    first_legacy_mix_exit_at: Optional[float] = None
    first_interrupted_mix_exit_at: Optional[float] = None
    first_main_hv_at: Optional[float] = None
    first_v2_finish_reversal: Optional[Dict[str, Any]] = None
    first_v2_mix_finish_reversal: Optional[Dict[str, Any]] = None
    signal_config: Optional[Dict[str, Any]] = None
    signal_config_changed = False

    confirmed_reversal_at: List[float] = []
    reversal_delta_a: List[float] = []
    reversal_delta_c_rate: List[float] = []
    reversal_delta_over_imin: List[float] = []
    reversal_threshold_a: List[float] = []
    reversal_threshold_c_rate: List[float] = []
    reversal_threshold_over_imin: List[float] = []
    reversal_imin_c_rate: List[float] = []
    reversal_by_stage: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        ts = float(row["timestamp_s"])
        before = str(row["stage"] or "")
        after = str(row["legacy_stage_after"] or "")
        before_key = _normalize_stage(before)
        after_key = _normalize_stage(after)
        shadow = _load_shadow_json(row["shadow_json"])

        captured_config = shadow.get("signal_config")
        if isinstance(captured_config, Mapping):
            current_config = dict(captured_config)
            if signal_config is None:
                signal_config = current_config
            elif current_config != signal_config:
                signal_config_changed = True

        first_stage = shadow.get("first_stage")
        if isinstance(first_stage, Mapping):
            state = str(first_stage.get("state") or "").strip()
            if state:
                first_stage_states[state] += 1

        decision = str(row["shadow_decision"] or "").strip()
        if decision:
            decisions[decision] += 1
        if decision == "finish_stage":
            reversal = _reversal_metrics(row, shadow)
            if first_v2_finish_at is None:
                first_v2_finish_at = ts
                first_v2_finish_reversal = reversal
            if before_key in MIX_STAGE_NAMES and first_v2_mix_finish_at is None:
                first_v2_mix_finish_at = ts
                first_v2_mix_finish_reversal = reversal

        events = shadow.get("events")
        if not isinstance(events, list):
            events = []
        if "current_reversal_confirmed" in events:
            confirmed_reversal_at.append(ts)
            reversal = _reversal_metrics(row, shadow)
            stage_bucket = reversal_by_stage.setdefault(
                before_key or "unknown",
                {
                    "timestamps": [],
                    "delta_a": [],
                    "delta_c_rate": [],
                    "delta_over_imin": [],
                    "threshold_a": [],
                    "threshold_c_rate": [],
                    "threshold_over_imin": [],
                    "threshold_source": Counter(),
                    "imin_c_rate": [],
                },
            )
            stage_bucket["timestamps"].append(ts)
            value = reversal["reversal_delta_a"]
            if value is not None:
                reversal_delta_a.append(value)
                stage_bucket["delta_a"].append(value)
            value = reversal["reversal_delta_c_rate"]
            if value is not None:
                reversal_delta_c_rate.append(value)
                stage_bucket["delta_c_rate"].append(value)
            value = reversal["reversal_delta_over_imin"]
            if value is not None:
                reversal_delta_over_imin.append(value)
                stage_bucket["delta_over_imin"].append(value)
            value = reversal["reversal_threshold_a"]
            if value is not None:
                reversal_threshold_a.append(value)
                stage_bucket["threshold_a"].append(value)
            value = reversal["reversal_threshold_c_rate"]
            if value is not None:
                reversal_threshold_c_rate.append(value)
                stage_bucket["threshold_c_rate"].append(value)
            value = reversal["reversal_threshold_over_imin"]
            if value is not None:
                reversal_threshold_over_imin.append(value)
                stage_bucket["threshold_over_imin"].append(value)
            source = reversal["reversal_threshold_source"]
            if source:
                threshold_sources[str(source)] += 1
                stage_bucket["threshold_source"][str(source)] += 1
            value = reversal["current_min_c_rate"]
            if value is not None:
                reversal_imin_c_rate.append(value)
                stage_bucket["imin_c_rate"].append(value)

        disagreement = str(row["disagreement"] or "").strip()
        if disagreement:
            disagreements[disagreement] += 1

        if str(row["shadow_status"] or "").lower() == "error":
            shadow_errors += 1

        audit_code = str(row["transition_audit_code"] or "").strip()
        audit_severity = str(row["transition_audit_severity"] or "").strip()
        if audit_code:
            audit_codes[audit_code] += 1
        if audit_severity:
            audit_severities[audit_severity] += 1

        if after and before_key != after_key:
            transition_name = f"{before} -> {after}"
            legacy_transitions[transition_name] += 1
            if _stage_kind(before) == "main" and _stage_kind(after) == "hv" and first_main_hv_at is None:
                first_main_hv_at = ts
            if before_key in MIX_STAGE_NAMES:
                if _is_terminal_mix_exit(after):
                    terminal_mix_transitions[transition_name] += 1
                    if first_legacy_mix_exit_at is None:
                        first_legacy_mix_exit_at = ts
                else:
                    interrupted_mix_transitions[transition_name] += 1
                    if first_interrupted_mix_exit_at is None:
                        first_interrupted_mix_exit_at = ts

        noteworthy = (
            str(row["shadow_status"] or "").lower() == "error"
            or bool(disagreement)
            or audit_severity in {"review", "safety"}
            or decision in {"finish_stage", "rest_and_diagnose", "pause_thermal", "hold_output_off"}
        )
        if noteworthy and len(calibration_samples) < max(1, int(max_calibration_samples)):
            calibration_samples.append(_sample_summary(row, shadow))

    first = rows[0]
    finish_lead_s: Optional[float] = None
    if first_v2_mix_finish_at is not None and first_legacy_mix_exit_at is not None:
        finish_lead_s = first_legacy_mix_exit_at - first_v2_mix_finish_at

    return {
        "session": {
            "session_id": str(session_id),
            "battery_id": first["battery_id"],
            "battery_type": first["battery_type"],
            "capacity_ah": first["capacity_ah"],
            "intent": first["intent"],
            "condition_before": first["condition_before"],
            "started_at": float(first["started_at"]),
            "first_sample_at": float(rows[0]["timestamp_s"]),
            "last_sample_at": float(rows[-1]["timestamp_s"]),
        },
        "samples": {
            "total": len(rows),
            "shadow_errors": shadow_errors,
        },
        "signal_config": {
            "captured": signal_config,
            "changed_within_session": signal_config_changed,
        },
        "shadow_decisions": dict(decisions),
        "disagreements": dict(disagreements),
        "first_stage_states": dict(first_stage_states),
        "transition_audits": {
            "severity": dict(audit_severities),
            "codes": dict(audit_codes),
        },
        "legacy_transitions": dict(legacy_transitions),
        "mix_exits": {
            "terminal_count": sum(terminal_mix_transitions.values()),
            "interrupted_count": sum(interrupted_mix_transitions.values()),
            "terminal_transitions": dict(terminal_mix_transitions),
            "interrupted_transitions": dict(interrupted_mix_transitions),
            "first_terminal_at": first_legacy_mix_exit_at,
            "first_interrupted_at": first_interrupted_mix_exit_at,
        },
        "hv_reversal": {
            "confirmed_count": len(confirmed_reversal_at),
            "first_confirmed_at": confirmed_reversal_at[0] if confirmed_reversal_at else None,
            "reversal_delta_a": _distribution(reversal_delta_a),
            "reversal_delta_c_rate": _distribution(reversal_delta_c_rate),
            "reversal_delta_over_imin": _distribution(reversal_delta_over_imin),
            "reversal_threshold_a": _distribution(reversal_threshold_a),
            "reversal_threshold_c_rate": _distribution(reversal_threshold_c_rate),
            "reversal_threshold_over_imin": _distribution(reversal_threshold_over_imin),
            "threshold_source": dict(threshold_sources),
            "current_min_c_rate": _distribution(reversal_imin_c_rate),
            "by_stage": _render_stage_reversal(reversal_by_stage),
            "first_v2_finish_reversal": first_v2_finish_reversal,
            "first_v2_mix_finish_reversal": first_v2_mix_finish_reversal,
        },
        "timing": {
            "first_main_to_hv_at": first_main_hv_at,
            "first_v2_finish_stage_at": first_v2_finish_at,
            "first_v2_mix_finish_at": first_v2_mix_finish_at,
            "first_legacy_mix_exit_at": first_legacy_mix_exit_at,
            "first_interrupted_mix_exit_at": first_interrupted_mix_exit_at,
            "v2_finish_lead_seconds": finish_lead_s,
        },
        "calibration_samples": calibration_samples,
    }
