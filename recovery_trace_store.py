from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, List, Mapping, Optional

from database import get_db
from pb_domain import BatteryCondition, ChargeIntent
from signal_analyzer import SignalAnalyzerConfig


TRACE_TABLE = "recovery_trace_points"
TRACE_RETENTION_DAYS = 180
TRACE_RETENTION_SWEEP_SEC = 24 * 3600
_last_retention_cleanup_s = 0.0


def _finite_or_none(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _bool_to_db(value: Any) -> Optional[int]:
    if value is None:
        return None
    if value is True:
        return 1
    if value is False:
        return 0
    raw = str(value).strip().lower()
    if raw in {"on", "true", "1"}:
        return 1
    if raw in {"off", "false", "0"}:
        return 0
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _enrich_signal_calibration(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Freeze the signal-threshold semantics used when this sample was captured.

    ChargeControllerV2 historically did not expose `reversal_threshold_a` in its
    public shadow payload even though SignalAnalyzer computes it. RecoverySessionTracker
    uses the default SignalAnalyzerConfig, so the trace store can reconstruct that exact
    threshold at capture time and persist the config alongside it. This avoids later
    replay tools silently applying a newer threshold policy to old measurements.
    """
    config = SignalAnalyzerConfig()
    snapshot["signal_config"] = {
        "reversal_ratio": config.reversal_ratio,
        "reversal_abs_floor_a": config.reversal_abs_a,
        "current_min_update_hysteresis_a": config.current_min_update_hysteresis_a,
        "plateau_abs_span_a": config.plateau_abs_span_a,
        "plateau_rel_span": config.plateau_rel_span,
        "voltage_max_update_hysteresis_v": config.voltage_max_update_hysteresis_v,
        "voltage_reversal_abs_v": config.voltage_reversal_abs_v,
        "voltage_reversal_confirmations": config.voltage_reversal_confirmations,
    }

    metrics = snapshot.get("metrics")
    if not isinstance(metrics, dict):
        return snapshot

    existing_threshold = _finite_or_none(metrics.get("reversal_threshold_a"))
    if existing_threshold is not None:
        metrics["reversal_threshold_source"] = "analyzer"
        return snapshot

    current_min_a = _finite_or_none(metrics.get("current_min_a"))
    if current_min_a is None:
        metrics["reversal_threshold_a"] = None
        metrics["reversal_threshold_source"] = "unavailable_without_imin"
        return snapshot

    relative_threshold = current_min_a * config.reversal_ratio
    threshold = max(config.reversal_abs_a, relative_threshold)
    metrics["reversal_threshold_a"] = threshold
    metrics["reversal_threshold_source"] = (
        "relative_to_imin"
        if relative_threshold >= config.reversal_abs_a
        else "instrument_floor"
    )
    return snapshot


async def init_recovery_trace_store() -> None:
    db = await get_db()
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TRACE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            started_at REAL NOT NULL,
            battery_id TEXT NOT NULL,
            battery_type TEXT NOT NULL DEFAULT '',
            capacity_ah REAL,
            intent TEXT NOT NULL DEFAULT 'recovery',
            condition_before TEXT NOT NULL DEFAULT 'unknown',
            timestamp_s REAL NOT NULL,
            stage TEXT NOT NULL,
            legacy_stage_after TEXT NOT NULL DEFAULT '',
            voltage_v REAL,
            current_a REAL,
            temp_c REAL,
            is_cv INTEGER NOT NULL DEFAULT 0,
            is_cc INTEGER,
            target_voltage_v REAL,
            ah REAL,
            output_on INTEGER,
            shadow_status TEXT NOT NULL DEFAULT '',
            shadow_decision TEXT,
            shadow_reason TEXT,
            legacy_effect TEXT,
            disagreement TEXT,
            transition_audit_code TEXT,
            transition_audit_severity TEXT,
            shadow_json TEXT NOT NULL DEFAULT '{{}}',
            UNIQUE(session_id, timestamp_s)
        )
        """
    )
    await db.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TRACE_TABLE}_session_time "
        f"ON {TRACE_TABLE}(session_id, timestamp_s)"
    )
    await db.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TRACE_TABLE}_latest "
        f"ON {TRACE_TABLE}(timestamp_s DESC)"
    )
    await db.commit()


async def cleanup_old_trace_points(
    *,
    now_s: Optional[float] = None,
    retention_days: int = TRACE_RETENTION_DAYS,
) -> int:
    """Delete raw diagnostic samples older than the retention window.

    Summarized recovery-cycle evidence lives in `recovery_cycles` and is not touched.
    Raw 30-second traces are intentionally bounded so shadow diagnostics cannot grow
    `rd6018.db` forever.
    """
    if int(retention_days) <= 0:
        raise ValueError("retention_days must be positive")
    reference = float(time.time() if now_s is None else now_s)
    cutoff = reference - int(retention_days) * 86400.0
    await init_recovery_trace_store()
    db = await get_db()
    cursor = await db.execute(
        f"DELETE FROM {TRACE_TABLE} WHERE timestamp_s < ?",
        (cutoff,),
    )
    await db.commit()
    deleted = int(cursor.rowcount) if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
    await cursor.close()
    return deleted


async def record_shadow_trace(
    *,
    session_id: str,
    started_at: float,
    battery_id: str,
    battery_type: str,
    capacity_ah: float,
    intent: ChargeIntent | str,
    condition_before: BatteryCondition | str,
    shadow: Mapping[str, Any],
) -> bool:
    """Persist one exact live sample plus its capture-time analyzer semantics.

    `(session_id, timestamp_s)` is idempotent so a retry of the same poll updates the
    sample instead of creating a fake second observation.
    """
    global _last_retention_cleanup_s

    trace = shadow.get("trace_point")
    if not isinstance(trace, Mapping):
        raise ValueError("shadow.trace_point is required")

    timestamp_s = _finite_or_none(trace.get("timestamp_s"))
    stage = str(trace.get("stage") or "").strip()
    if timestamp_s is None or not stage:
        raise ValueError("trace_point requires finite timestamp_s and stage")

    session_id = str(session_id).strip()
    battery_id = str(battery_id).strip()
    if not session_id:
        raise ValueError("session_id is required")
    if not battery_id:
        raise ValueError("battery_id is required")

    audit = shadow.get("transition_audit")
    if not isinstance(audit, Mapping):
        audit = {}

    intent_value = getattr(intent, "value", intent)
    condition_value = getattr(condition_before, "value", condition_before)
    safe_shadow = _enrich_signal_calibration(_json_safe(dict(shadow)))
    shadow_json = json.dumps(
        safe_shadow,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )

    await init_recovery_trace_store()
    db = await get_db()
    await db.execute(
        f"""
        INSERT INTO {TRACE_TABLE} (
            session_id, started_at, battery_id, battery_type, capacity_ah,
            intent, condition_before, timestamp_s, stage, legacy_stage_after,
            voltage_v, current_a, temp_c, is_cv, is_cc, target_voltage_v, ah,
            output_on, shadow_status, shadow_decision, shadow_reason,
            legacy_effect, disagreement, transition_audit_code,
            transition_audit_severity, shadow_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, timestamp_s) DO UPDATE SET
            started_at=excluded.started_at,
            battery_id=excluded.battery_id,
            battery_type=excluded.battery_type,
            capacity_ah=excluded.capacity_ah,
            intent=excluded.intent,
            condition_before=excluded.condition_before,
            stage=excluded.stage,
            legacy_stage_after=excluded.legacy_stage_after,
            voltage_v=excluded.voltage_v,
            current_a=excluded.current_a,
            temp_c=excluded.temp_c,
            is_cv=excluded.is_cv,
            is_cc=excluded.is_cc,
            target_voltage_v=excluded.target_voltage_v,
            ah=excluded.ah,
            output_on=excluded.output_on,
            shadow_status=excluded.shadow_status,
            shadow_decision=excluded.shadow_decision,
            shadow_reason=excluded.shadow_reason,
            legacy_effect=excluded.legacy_effect,
            disagreement=excluded.disagreement,
            transition_audit_code=excluded.transition_audit_code,
            transition_audit_severity=excluded.transition_audit_severity,
            shadow_json=excluded.shadow_json
        """,
        (
            session_id,
            float(started_at),
            battery_id,
            str(battery_type or ""),
            _finite_or_none(capacity_ah),
            str(intent_value),
            str(condition_value),
            timestamp_s,
            stage,
            str(trace.get("legacy_stage_after") or ""),
            _finite_or_none(trace.get("voltage_v")),
            _finite_or_none(trace.get("current_a")),
            _finite_or_none(trace.get("temp_c")),
            1 if bool(trace.get("is_cv", False)) else 0,
            _bool_to_db(trace.get("is_cc")),
            _finite_or_none(trace.get("target_voltage_v")),
            _finite_or_none(trace.get("ah")),
            _bool_to_db(trace.get("output_on")),
            str(shadow.get("status") or ""),
            str(shadow.get("decision")) if shadow.get("decision") is not None else None,
            str(shadow.get("reason")) if shadow.get("reason") is not None else None,
            str(shadow.get("legacy_effect")) if shadow.get("legacy_effect") is not None else None,
            str(shadow.get("disagreement")) if shadow.get("disagreement") is not None else None,
            str(audit.get("code")) if audit.get("code") is not None else None,
            str(audit.get("severity")) if audit.get("severity") is not None else None,
            shadow_json,
        ),
    )

    # Sweep at most once per day per process. The first live sample after restart
    # performs the sweep, which also makes retention independent of bot uptime.
    if (
        _last_retention_cleanup_s <= 0
        or timestamp_s - _last_retention_cleanup_s >= TRACE_RETENTION_SWEEP_SEC
    ):
        cutoff = timestamp_s - TRACE_RETENTION_DAYS * 86400.0
        await db.execute(
            f"DELETE FROM {TRACE_TABLE} WHERE timestamp_s < ?",
            (cutoff,),
        )
        _last_retention_cleanup_s = timestamp_s

    await db.commit()
    return True


async def list_trace_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    await init_recovery_trace_store()
    db = await get_db()
    async with db.execute(
        f"""
        SELECT
            session_id,
            battery_id,
            battery_type,
            capacity_ah,
            intent,
            condition_before,
            MIN(started_at) AS started_at,
            MIN(timestamp_s) AS first_sample_at,
            MAX(timestamp_s) AS last_sample_at,
            COUNT(*) AS sample_count,
            SUM(CASE WHEN shadow_status = 'error' THEN 1 ELSE 0 END) AS shadow_error_count,
            SUM(CASE WHEN disagreement IS NOT NULL AND disagreement != '' THEN 1 ELSE 0 END) AS disagreement_count,
            SUM(CASE WHEN transition_audit_severity IN ('review', 'safety') THEN 1 ELSE 0 END) AS transition_review_count
        FROM {TRACE_TABLE}
        GROUP BY session_id
        ORDER BY last_sample_at DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def latest_trace_session_id() -> Optional[str]:
    sessions = await list_trace_sessions(limit=1)
    return str(sessions[0]["session_id"]) if sessions else None


async def export_replay_document(session_id: str) -> Dict[str, Any]:
    """Export one captured live session directly into recovery_replay format."""
    await init_recovery_trace_store()
    db = await get_db()
    async with db.execute(
        f"SELECT * FROM {TRACE_TABLE} WHERE session_id = ? ORDER BY timestamp_s ASC, id ASC",
        (str(session_id),),
    ) as cursor:
        rows = await cursor.fetchall()
    if not rows:
        raise KeyError(f"unknown trace session: {session_id}")

    first = rows[0]
    trace: List[Dict[str, Any]] = []
    skipped_invalid = 0
    for row in rows:
        required = (row["voltage_v"], row["current_a"], row["temp_c"])
        if any(value is None for value in required):
            skipped_invalid += 1
            continue
        point: Dict[str, Any] = {
            "timestamp_s": float(row["timestamp_s"]),
            "stage": row["stage"],
            "voltage_v": float(row["voltage_v"]),
            "current_a": float(row["current_a"]),
            "temp_c": float(row["temp_c"]),
            "is_cv": bool(row["is_cv"]),
            "is_cc": (bool(row["is_cc"]) if row["is_cc"] is not None else not bool(row["is_cv"])),
        }
        if row["target_voltage_v"] is not None:
            point["target_voltage_v"] = float(row["target_voltage_v"])
        if row["ah"] is not None:
            point["ah"] = float(row["ah"])
        trace.append(point)

    if not trace:
        raise ValueError(f"trace session {session_id} has no replayable U/I/T samples")

    cycle = {
        "battery_id": first["battery_id"],
        "started_at": float(first["started_at"]),
        "intent": first["intent"] or ChargeIntent.RECOVERY.value,
        "condition_before": first["condition_before"] or BatteryCondition.UNKNOWN.value,
        "trace": trace,
        "outcome": "captured_live_trace",
        "notes": (
            f"exported from {TRACE_TABLE}; stored={len(rows)} replayable={len(trace)} "
            f"skipped_invalid={skipped_invalid}"
        ),
    }
    return {
        "cycles": [cycle],
        "trace_export": {
            "session_id": str(session_id),
            "battery_type": first["battery_type"],
            "capacity_ah": first["capacity_ah"],
            "stored_samples": len(rows),
            "replayable_samples": len(trace),
            "skipped_invalid_samples": skipped_invalid,
        },
    }
