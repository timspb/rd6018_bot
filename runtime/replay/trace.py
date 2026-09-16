"""Decision trace and replay comparison models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class DecisionTrace:
    timestamp: float
    stage: Any
    phase: Any
    telemetry_snapshot: Any
    charge_intent: Any
    safety_decision: Any
    execution_decision: Any
    journal_events: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ReplayComparison:
    status: str
    fields: tuple[str, ...] = ()
    expected: Mapping[str, Any] = field(default_factory=dict)
    actual: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""


class ReplayComparator:
    @staticmethod
    def compare(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> ReplayComparison:
        fields = tuple(sorted(key for key in set(expected) | set(actual) if expected.get(key) != actual.get(key)))
        if not expected:
            return ReplayComparison("INCONCLUSIVE", (), dict(expected), dict(actual), "expected_checkpoint_missing")
        return ReplayComparison("MATCH" if not fields else "MISMATCH", fields, dict(expected), dict(actual), "equal" if not fields else "fields_differ")
