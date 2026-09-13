"""Decision-only parity comparison between V2-shaped data and V3 results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from runtime.output.intent import SafeOutputIntent
from runtime.safety.engine import SafetyDecision

from ..intent import ChargeIntent


class ParityStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class LegacyDecisionSnapshot:
    phase: str | None
    stage: str | None
    transition: str | None
    completed: bool
    enable: bool | None
    target_voltage: float | None
    target_current: float | None
    safety_allowed: bool | None = None
    violations: tuple[str, ...] = ()


class LegacyDecisionAdapter:
    """Adapt a V2 decision mapping only; never invoke its producer."""

    def from_mapping(self, decision: Mapping[str, Any]) -> LegacyDecisionSnapshot:
        target_voltage = decision.get("target_voltage", decision.get("set_voltage"))
        target_current = decision.get("target_current", decision.get("set_current"))
        violations = decision.get("violations", ())
        return LegacyDecisionSnapshot(
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


@dataclass(frozen=True)
class V3DecisionSnapshot:
    phase: str | None
    stage: str | None
    transition: str | None
    completed: bool
    enable: bool | None
    target_voltage: float | None
    target_current: float | None
    safety_allowed: bool
    violations: tuple[str, ...]

    @classmethod
    def from_decisions(cls, intent: ChargeIntent, safety: SafetyDecision, output: SafeOutputIntent | None = None) -> "V3DecisionSnapshot":
        return cls(
            phase=intent.next_stage,
            stage=intent.next_stage,
            transition=intent.reason if safety.allowed else safety.reason,
            completed=intent.completed,
            enable=None if output is None else output.action.value == "enable_output",
            target_voltage=None if output is None else output.target_voltage,
            target_current=None if output is None else output.target_current,
            safety_allowed=safety.allowed,
            violations=tuple(item.type for item in safety.violations),
        )


@dataclass(frozen=True)
class DecisionParityResult:
    status: ParityStatus
    fields: tuple[str, ...]
    v2_decision: LegacyDecisionSnapshot
    v3_decision: V3DecisionSnapshot
    reason: str | None = None


class DecisionParityComparator:
    FIELDS = ("phase", "stage", "transition", "completed", "enable", "target_voltage", "target_current", "safety_allowed", "violations")

    def compare(self, v2: LegacyDecisionSnapshot, v3: V3DecisionSnapshot) -> DecisionParityResult:
        mismatches = tuple(field for field in self.FIELDS if getattr(v2, field) != getattr(v3, field))
        return DecisionParityResult(
            ParityStatus.MATCH if not mismatches else ParityStatus.MISMATCH,
            mismatches,
            v2,
            v3,
            None if not mismatches else "decision fields differ",
        )
