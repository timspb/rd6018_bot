"""V2/V3 decision comparison contracts for Phase 9.0.

This module compares already-produced decision snapshots. It does not run a
controller, dispatch an actuator intent, or call any transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


class ComparisonStatus(str, Enum):
    EQUAL = "equal"
    EXPECTED_DIFFERENCE = "expected_difference"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ComparisonContext:
    """The same input snapshot passed to both decision providers."""

    trace_id: str
    telemetry: Any
    configuration: Any
    session_context: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id is required")
        object.__setattr__(self, "session_context", _freeze(self.session_context))


@dataclass(frozen=True)
class DecisionSnapshot:
    """Comparable V2/V3 output; actuator intent is represented, never executed."""

    fsm_state: str | None
    phase: str | None
    profile: str | None
    strategy_decision: Mapping[str, Any]
    target_values: Mapping[str, Any]
    safety_limits: Mapping[str, Any]
    warnings: tuple[str, ...] = ()
    containment_recommendation: str | None = None
    actuator_intent: Mapping[str, Any] | None = None
    trace_id: str = ""

    def __post_init__(self) -> None:
        for name in ("strategy_decision", "target_values", "safety_limits"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, _freeze(value))
        if self.actuator_intent is not None:
            if not isinstance(self.actuator_intent, Mapping):
                raise TypeError("actuator_intent must be a mapping or None")
            object.__setattr__(self, "actuator_intent", _freeze(self.actuator_intent))


@dataclass(frozen=True)
class ComparisonDifference:
    field: str
    v2: Any
    v3: Any
    classification: ComparisonStatus


@dataclass(frozen=True)
class ComparisonResult:
    status: ComparisonStatus
    trace_id: str
    equal: bool
    differences: tuple[ComparisonDifference, ...]
    v2: DecisionSnapshot | None
    v3: DecisionSnapshot | None


DecisionProvider = Callable[[ComparisonContext], DecisionSnapshot | None]


class V2V3ComparisonEngine:
    """Run two decision providers in comparison mode only."""

    _FIELDS = (
        "fsm_state", "phase", "profile", "strategy_decision", "target_values",
        "safety_limits", "warnings", "containment_recommendation", "actuator_intent",
    )

    def __init__(self, v2_provider: DecisionProvider, v3_provider: DecisionProvider, *, expected_differences: set[str] | frozenset[str] = frozenset()) -> None:
        self._v2_provider = v2_provider
        self._v3_provider = v3_provider
        self._expected_differences = frozenset(expected_differences)

    def compare(self, context: ComparisonContext) -> ComparisonResult:
        v2 = self._v2_provider(context)
        v3 = self._v3_provider(context)
        if v2 is None or v3 is None:
            return ComparisonResult(ComparisonStatus.UNKNOWN, context.trace_id, False, (), v2, v3)
        differences = []
        for field in self._FIELDS:
            left, right = getattr(v2, field), getattr(v3, field)
            if left != right:
                status = ComparisonStatus.EXPECTED_DIFFERENCE if field in self._expected_differences else ComparisonStatus.CONFLICT
                differences.append(ComparisonDifference(field, left, right, status))
        if not differences:
            status = ComparisonStatus.EQUAL
        elif all(item.classification is ComparisonStatus.EXPECTED_DIFFERENCE for item in differences):
            status = ComparisonStatus.EXPECTED_DIFFERENCE
        else:
            status = ComparisonStatus.CONFLICT
        return ComparisonResult(status, context.trace_id, status is ComparisonStatus.EQUAL, tuple(differences), v2, v3)


__all__ = [
    "ComparisonStatus", "ComparisonContext", "DecisionSnapshot",
    "ComparisonDifference", "ComparisonResult", "V2V3ComparisonEngine",
]
