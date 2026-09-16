"""Data contracts for native program decision validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Tuple

from ..battery import BatteryProfile
from ..intent import ChargeIntent
from ..measurements import Measurements
from ..program import ChargeProgram
from ..state import ChargeState


@dataclass(frozen=True)
class ChargeDecisionCase:
    case_id: str
    battery_profile: BatteryProfile
    measurements: Measurements
    charge_state: ChargeState
    input_config: Mapping[str, Any]
    expected_intent: ChargeIntent


@dataclass(frozen=True)
class DecisionMismatch:
    field: str
    expected: Any
    actual: Any
    reason: str


class DecisionValidationStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class DecisionValidationResult:
    status: DecisionValidationStatus
    case_id: str
    expected: ChargeIntent
    actual: ChargeIntent
    mismatches: Tuple[DecisionMismatch, ...] = ()

    @classmethod
    def compare(cls, case: ChargeDecisionCase, actual: ChargeIntent) -> "DecisionValidationResult":
        fields = ("target_voltage", "target_current", "next_stage", "completed", "reason")
        mismatches = tuple(
            DecisionMismatch(field, getattr(case.expected_intent, field), getattr(actual, field), "decision differs")
            for field in fields
            if getattr(case.expected_intent, field) != getattr(actual, field)
        )
        status = DecisionValidationStatus.MATCH if not mismatches else DecisionValidationStatus.MISMATCH
        return cls(status, case.case_id, case.expected_intent, actual, mismatches)


def validate_case(case: ChargeDecisionCase, program: ChargeProgram) -> DecisionValidationResult:
    """Evaluate one native program against its fixed expected intent."""
    actual = program.evaluate(case.charge_state, case.measurements)
    return DecisionValidationResult.compare(case, actual)
