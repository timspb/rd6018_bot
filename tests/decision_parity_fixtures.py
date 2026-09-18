"""Test-only translation oracle for V2-shaped decision mappings."""

from __future__ import annotations

from typing import Any, Mapping

from runtime.charge.shadow import V2DecisionSnapshot


def from_mapping(decision: Mapping[str, Any]) -> V2DecisionSnapshot:
    target_voltage = decision.get("target_voltage", decision.get("set_voltage"))
    target_current = decision.get("target_current", decision.get("set_current"))
    violations = decision.get("violations", ())
    return V2DecisionSnapshot(
        phase=decision.get("phase", decision.get("mode")),
        stage=decision.get("stage", decision.get("next_stage")),
        transition=decision.get("transition", decision.get("reason")),
        completed=bool(decision.get("completed", decision.get("complete", False))),
        enable=decision.get("enable", decision.get("output_enabled")),
        target_voltage=target_voltage,
        target_current=target_current,
        safety_allowed=decision.get("safety_allowed", decision.get("allowed")),
        violations=tuple(str(item) for item in violations),
    )
