"""Immutable safety inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

class SafetyState(str, Enum):
    ALLOW = "ALLOW"
    LIMIT = "LIMIT"
    DENY = "DENY"
    EMERGENCY = "EMERGENCY"


@dataclass(frozen=True)
class SafetyContext:
    voltage_v: float | None
    current_a: float | None
    temperatures_c: Tuple[float | None, ...]
    protection_codes: Tuple[str, ...]
    telemetry_fresh: bool
    telemetry_present: bool
    decision_context: "DecisionContext | None" = None
    emergency: bool = False
    timestamp: float = 0.0


@dataclass(frozen=True)
class DecisionContext:
    source_decision_id: str
    requested_voltage_v: float
    requested_current_a: float
    requested_mode: str


@dataclass(frozen=True)
class SafetyDecision:
    state: SafetyState
    reason: str
    triggered_rules: Tuple[str, ...]
    confidence: str
    timestamp: float

    def __post_init__(self) -> None:
        if not self.reason.strip() or not self.confidence.strip():
            raise ValueError("safety decision reason and confidence are required")


__all__ = ["DecisionContext", "SafetyContext", "SafetyDecision", "SafetyState"]
