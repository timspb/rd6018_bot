"""Test-only translation oracle for legacy decision mappings."""

from __future__ import annotations

from typing import Any, Mapping

from runtime.charge import ChargeIntent


def legacy_mapping_to_intent(result: Mapping[str, Any]) -> ChargeIntent:
    """Preserve the old mapping semantics without a production adapter."""
    forbidden = {"turn_on", "turn_off", "emergency_stop", "full_reset"}
    if forbidden.intersection(result):
        raise ValueError("legacy actuator commands cannot cross the program boundary")
    return ChargeIntent(
        target_voltage=result.get("target_voltage", result.get("set_voltage")),
        target_current=result.get("target_current", result.get("set_current")),
        next_stage=result.get("next_stage"),
        completed=bool(result.get("completed", False)),
        reason=str(result.get("reason", result.get("log_event", ""))),
    )
