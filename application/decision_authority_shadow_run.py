"""EPIC K decision-authority shadow rehearsal; no live takeover or execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from .v2_v3_comparison import ComparisonContext, ComparisonResult, DecisionSnapshot, V2V3ComparisonEngine


class ShadowRunStatus(str, Enum):
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class ShadowFailure(str, Enum):
    V3_UNAVAILABLE = "v3_unavailable"
    BAD_DECISION = "bad_decision"
    STALE_TELEMETRY = "stale_telemetry"
    CONFIG_CONFLICT = "config_conflict"
    ROLLBACK_REQUEST = "rollback_request"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ShadowDecisionProvenance:
    trace_id: str
    authority: str
    mode: str
    source: str
    reason: str


@dataclass(frozen=True)
class ShadowTransitionEvent:
    event_type: str
    timestamp: datetime
    current_authority: str
    candidate_authority: str
    approval_state: str
    rollback_state: str
    reason: str


@dataclass(frozen=True)
class ExecutionHandoffPreparation:
    prepared: bool
    execution_owner: str
    source_decision_authority: str
    decision: Any
    dispatched: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", _freeze(self.decision))
        if self.dispatched:
            raise ValueError("shadow handoff cannot be dispatched")


@dataclass(frozen=True)
class DecisionAuthorityShadowRun:
    status: ShadowRunStatus
    trace_id: str
    current_authority: str
    candidate_authority: str
    approval_state: str
    rollback_state: str
    v2_decision: DecisionSnapshot | None
    v3_canonical_decision: DecisionSnapshot | None
    comparison: ComparisonResult
    provenance: ShadowDecisionProvenance | None
    handoff: ExecutionHandoffPreparation | None
    failure: ShadowFailure | None
    transition_history: tuple[ShadowTransitionEvent, ...]
    live_decision_ownership_changed: bool = False


class DecisionAuthorityShadowRunner:
    """Rehearse future Stage 1 while keeping V2 authoritative."""

    def __init__(self, *, expected_differences: set[str] | frozenset[str] = frozenset()) -> None:
        self._expected_differences = frozenset(expected_differences)
        self._history: list[ShadowTransitionEvent] = []
        self._current_authority = "V2"
        self._candidate_authority = "V3"
        self._approval_state = "NOT_APPROVED_SHADOW_ONLY"
        self._rollback_state = "NOT_REQUESTED"

    @property
    def transition_history(self) -> tuple[ShadowTransitionEvent, ...]:
        return tuple(self._history)

    def run(
        self,
        context: ComparisonContext,
        v2_decision: DecisionSnapshot | None,
        v3_decision: DecisionSnapshot | None,
        *,
        failure: ShadowFailure | None = None,
    ) -> DecisionAuthorityShadowRun:
        if not isinstance(context, ComparisonContext):
            raise TypeError("ComparisonContext is required")
        if failure is ShadowFailure.V3_UNAVAILABLE:
            v3_decision = None
        comparison = V2V3ComparisonEngine(
            lambda _context: v2_decision,
            lambda _context: v3_decision,
            expected_differences=self._expected_differences,
        ).compare(context)

        self._rollback_state = "REQUESTED" if failure is ShadowFailure.ROLLBACK_REQUEST else "NOT_REQUESTED"
        status = self._status(comparison, failure, v3_decision)
        candidate = None if status is ShadowRunStatus.BLOCKED else v3_decision
        provenance = None
        handoff = None
        if candidate is not None:
            provenance = ShadowDecisionProvenance(
                context.trace_id, "V3", "shadow_stage1_rehearsal",
                "decision-authority-shadow-run", "canonical_candidate_not_authoritative",
            )
            handoff = ExecutionHandoffPreparation(True, "V2", "V3", candidate.actuator_intent)
        self._record(
            "shadow_rehearsal_completed",
            "rollback requested" if failure is ShadowFailure.ROLLBACK_REQUEST else status.value.lower(),
        )
        return DecisionAuthorityShadowRun(
            status, context.trace_id, self._current_authority, self._candidate_authority,
            self._approval_state, self._rollback_state, v2_decision, candidate,
            comparison, provenance, handoff, failure, self.transition_history, False,
        )

    def _status(
        self,
        comparison: ComparisonResult,
        failure: ShadowFailure | None,
        v3_decision: DecisionSnapshot | None,
    ) -> ShadowRunStatus:
        if failure in {
            ShadowFailure.V3_UNAVAILABLE,
            ShadowFailure.BAD_DECISION,
            ShadowFailure.STALE_TELEMETRY,
            ShadowFailure.CONFIG_CONFLICT,
            ShadowFailure.ROLLBACK_REQUEST,
        } or v3_decision is None:
            return ShadowRunStatus.BLOCKED
        if comparison.status.value == "conflict":
            return ShadowRunStatus.BLOCKED
        if comparison.status.value == "expected_difference":
            return ShadowRunStatus.WARNING
        return ShadowRunStatus.READY

    def _record(self, event_type: str, reason: str) -> None:
        self._history.append(ShadowTransitionEvent(
            event_type, datetime.now(timezone.utc), self._current_authority,
            self._candidate_authority, self._approval_state, self._rollback_state, reason,
        ))


__all__ = [
    "ShadowRunStatus", "ShadowFailure", "ShadowDecisionProvenance",
    "ShadowTransitionEvent", "ExecutionHandoffPreparation",
    "DecisionAuthorityShadowRun", "DecisionAuthorityShadowRunner",
]
