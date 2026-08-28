from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from battery_registry import RecoveryCycleEvidence
from pb_domain import BatteryCondition, ChargeIntent
from recovery_session import RecoverySessionTracker, RecoveryTracePoint
from recovery_trends import analyze_recovery_trend


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def evidence_to_dict(evidence: RecoveryCycleEvidence) -> Dict[str, Any]:
    data = asdict(evidence)
    data["intent"] = _enum_value(evidence.intent)
    data["condition_before"] = _enum_value(evidence.condition_before)
    return data


def replay_cycle(document: Mapping[str, Any]) -> RecoveryCycleEvidence:
    points_raw = document.get("trace")
    if not isinstance(points_raw, list) or not points_raw:
        raise ValueError("cycle.trace must be a non-empty list")

    try:
        intent = ChargeIntent(str(document.get("intent", ChargeIntent.RECOVERY.value)))
        condition = BatteryCondition(
            str(document.get("condition_before", BatteryCondition.UNKNOWN.value))
        )
    except ValueError as exc:
        raise ValueError(f"invalid cycle enum value: {exc}") from exc

    started_at = float(document.get("started_at", points_raw[0]["timestamp_s"]))
    tracker = RecoverySessionTracker(
        battery_id=str(document["battery_id"]),
        started_at=started_at,
        intent=intent,
        condition_before=condition,
    )
    for raw in points_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("every trace point must be an object")
        tracker.observe(RecoveryTracePoint.from_mapping(raw))

    completed_at_raw = document.get("completed_at")
    completed_at = (
        float(completed_at_raw)
        if completed_at_raw is not None
        else float(points_raw[-1]["timestamp_s"])
    )
    return tracker.complete(
        completed_at=completed_at,
        outcome=str(document.get("outcome", "replayed")),
        measured_capacity_ah=(
            float(document["measured_capacity_ah"])
            if document.get("measured_capacity_ah") is not None
            else None
        ),
        cca_a=float(document["cca_a"]) if document.get("cca_a") is not None else None,
        internal_resistance_mohm=(
            float(document["internal_resistance_mohm"])
            if document.get("internal_resistance_mohm") is not None
            else None
        ),
        notes=str(document.get("notes", "")),
    )


def replay_document(document: Mapping[str, Any]) -> Dict[str, Any]:
    raw_cycles = document.get("cycles")
    if not isinstance(raw_cycles, list) or not raw_cycles:
        raise ValueError("document.cycles must be a non-empty list")

    cycles = [replay_cycle(cycle) for cycle in raw_cycles]
    trend = analyze_recovery_trend(cycles)
    return {
        "cycles": [evidence_to_dict(cycle) for cycle in cycles],
        "trend": {
            "status": trend.status.value,
            "confidence": trend.confidence.value,
            "score": trend.score,
            "cycles_considered": trend.cycles_considered,
            "reasons": list(trend.reasons),
            "metrics": [
                {
                    "name": metric.name,
                    "first": metric.first,
                    "last": metric.last,
                    "relative_change": metric.relative_change,
                    "score": metric.score,
                    "explanation": metric.explanation,
                }
                for metric in trend.metrics
            ],
        },
    }


def replay_json_file(path: str | Path) -> Dict[str, Any]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, Mapping):
        raise ValueError("replay document root must be an object")
    return replay_document(document)
