"""Stage 1 decision cutover readiness; no live ownership mutation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class ReadinessState(str, Enum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    APPROVED_CANDIDATE = "APPROVED_CANDIDATE"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class Stage1SafetyGates:
    shadow_acceptance_pass: bool
    no_unresolved_safety_conflicts: bool
    telemetry_healthy: bool
    configuration_stable: bool
    runtime_healthy: bool

    def missing(self) -> tuple[str, ...]:
        return tuple(name for name, value in (
            ("shadow_acceptance_pass", self.shadow_acceptance_pass),
            ("no_unresolved_safety_conflicts", self.no_unresolved_safety_conflicts),
            ("telemetry_healthy", self.telemetry_healthy),
            ("configuration_stable", self.configuration_stable),
            ("runtime_healthy", self.runtime_healthy),
        ) if not value)


@dataclass(frozen=True)
class Stage1ApprovalRecord:
    approval_id: str
    timestamp: datetime
    operator: str
    source: str
    explicit_enable: bool
    rollback_authority: str

    def __post_init__(self) -> None:
        for name in ("approval_id", "operator", "source", "rollback_authority"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime")
        if not self.explicit_enable:
            raise ValueError("explicit_enable is required")


@dataclass(frozen=True)
class DecisionAuthorityAuditEvent:
    event_type: str
    timestamp: datetime
    source: str
    previous_owner: str
    current_owner: str
    reason: str


@dataclass(frozen=True)
class DecisionCutoverReadiness:
    state: ReadinessState
    decision_owner: str
    execution_owner: str
    physical_owner: str
    gates: Stage1SafetyGates
    approval: Stage1ApprovalRecord | None
    missing_gates: tuple[str, ...]
    transition_history: tuple[DecisionAuthorityAuditEvent, ...]
    live_ownership_changed: bool = False


class DecisionCutoverReadinessModel:
    """Prepare and audit Stage 1 without changing any live authority."""

    def __init__(self) -> None:
        self._state = ReadinessState.NOT_READY
        self._decision_owner = "V2"
        self._execution_owner = "V2"
        self._physical_owner = "V2"
        self._gates = Stage1SafetyGates(False, False, False, False, False)
        self._approval: Stage1ApprovalRecord | None = None
        self._history: list[DecisionAuthorityAuditEvent] = []

    def prepare(self, gates: Stage1SafetyGates) -> DecisionCutoverReadiness:
        self._gates = gates
        self._approval = None
        self._state = ReadinessState.READY if not gates.missing() else ReadinessState.NOT_READY
        self._record("stage1_readiness_evaluated", "V2", "V2", "gates evaluated")
        return self.snapshot()

    def approve(self, *, operator: str, source: str, rollback_authority: str, timestamp: datetime | None = None) -> DecisionCutoverReadiness:
        if self._state is not ReadinessState.READY:
            raise PermissionError("Stage 1 safety gates are not satisfied")
        approval = Stage1ApprovalRecord(uuid4().hex, timestamp or datetime.now(timezone.utc), operator, source, True, rollback_authority)
        self._approval = approval
        self._state = ReadinessState.APPROVED_CANDIDATE
        self._decision_owner = "V3-candidate"
        self._record("stage1_decision_approval_recorded", "V2", "V3-candidate", "explicit approval recorded")
        return self.snapshot()

    def rollback(self, *, source: str, reason: str) -> DecisionCutoverReadiness:
        previous = self._decision_owner
        self._state = ReadinessState.ROLLED_BACK
        self._decision_owner = "V2"
        self._approval = None
        self._record("stage1_decision_rollback", previous, "V2", reason, source=source)
        return self.snapshot()

    def snapshot(self) -> DecisionCutoverReadiness:
        return DecisionCutoverReadiness(
            self._state, self._decision_owner, self._execution_owner, self._physical_owner,
            self._gates, self._approval, self._gates.missing(), tuple(self._history), False,
        )

    def _record(self, event_type: str, previous: str, current: str, reason: str, *, source: str = "decision-cutover-readiness") -> None:
        self._history.append(DecisionAuthorityAuditEvent(event_type, datetime.now(timezone.utc), source, previous, current, reason))


__all__ = [
    "ReadinessState", "Stage1SafetyGates", "Stage1ApprovalRecord",
    "DecisionAuthorityAuditEvent", "DecisionCutoverReadiness",
    "DecisionCutoverReadinessModel",
]
