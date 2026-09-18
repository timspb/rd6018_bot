"""Decision-only parity comparison between V2-shaped data and V3 results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from runtime.output.intent import SafeOutputIntent
from runtime.safety.engine import SafetyDecision

from ..intent import ChargeIntent


class ParityStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class V2DecisionSnapshot:
    phase: str | None
    stage: str | None
    transition: str | None
    completed: bool
    enable: bool | None
    target_voltage: float | None
    target_current: float | None
    safety_allowed: bool | None = None
    violations: tuple[str, ...] = ()


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
    v2_decision: V2DecisionSnapshot
    v3_decision: V3DecisionSnapshot
    reason: str | None = None

    @property
    def v2_snapshot(self) -> V2DecisionSnapshot:
        return self.v2_decision

    @property
    def v3_snapshot(self) -> V3DecisionSnapshot:
        return self.v3_decision


class DecisionParityComparator:
    FIELDS = ("phase", "stage", "transition", "completed", "enable", "target_voltage", "target_current", "safety_allowed", "violations")

    def compare(self, v2: V2DecisionSnapshot, v3: V3DecisionSnapshot) -> DecisionParityResult:
        mismatches = tuple(field for field in self.FIELDS if getattr(v2, field) != getattr(v3, field))
        return DecisionParityResult(
            ParityStatus.MATCH if not mismatches else ParityStatus.MISMATCH,
            mismatches,
            v2,
            v3,
            None if not mismatches else "decision fields differ",
        )
