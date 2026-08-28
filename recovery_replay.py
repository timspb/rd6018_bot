from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from battery_registry import RecoveryCycleEvidence
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecisionPolicy
from recovery_session import RecoverySessionTracker, RecoveryTracePoint
from recovery_trends import analyze_recovery_trend


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def evidence_to_dict(evidence: RecoveryCycleEvidence) -> Dict[str, Any]:
    data = asdict(evidence)
    data["intent"] = _enum_value(evidence.intent)
    data["condition_before"] = _enum_value(evidence.condition_before)
    return data


def _replay_cycle_internal(
    document: Mapping[str, Any],
) -> Tuple[RecoveryCycleEvidence, list[Dict[str, Any]]]:
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
    policy = RecoveryDecisionPolicy()
    decisions: list[Dict[str, Any]] = []

    for raw in points_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("every trace point must be an object")
        point = RecoveryTracePoint.from_mapping(raw)
        analysis = tracker.observe(point)
        result = policy.decide(
            analysis,
            stage=point.stage,
            intent=intent,
            output_is_on=True,
        )
        decisions.append(
            {
                "timestamp_s": point.timestamp_s,
                "stage": point.stage,
                "decision": result.decision.value,
                "reason": result.reason,
                "events": sorted(event.value for event in result.evidence),
            }
        )

    completed_at_raw = document.get("completed_at")
    completed_at = (
        float(completed_at_raw)
        if completed_at_raw is not None
        else float(points_raw[-1]["timestamp_s"])
    )
    evidence = tracker.complete(
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
    return evidence, decisions


def replay_cycle(document: Mapping[str, Any]) -> RecoveryCycleEvidence:
    evidence, _ = _replay_cycle_internal(document)
    return evidence


def replay_document(document: Mapping[str, Any]) -> Dict[str, Any]:
    raw_cycles = document.get("cycles")
    if not isinstance(raw_cycles, list) or not raw_cycles:
        raise ValueError("document.cycles must be a non-empty list")

    replayed = [_replay_cycle_internal(cycle) for cycle in raw_cycles]
    cycles = [item[0] for item in replayed]
    decision_traces = [item[1] for item in replayed]
    trend = analyze_recovery_trend(cycles)

    counts = Counter(
        row["decision"]
        for trace in decision_traces
        for row in trace
    )
    non_continue = [
        row
        for trace in decision_traces
        for row in trace
        if row["decision"] != "continue"
    ]

    return {
        "cycles": [evidence_to_dict(cycle) for cycle in cycles],
        "decision_traces": decision_traces,
        "decision_summary": {
            "counts": dict(sorted(counts.items())),
            "non_continue_count": len(non_continue),
            "first_non_continue": non_continue[0] if non_continue else None,
        },
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
