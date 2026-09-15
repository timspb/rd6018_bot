"""EPIC L operational readiness; approval and rollback are model-only."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from .decision_cutover_readiness import Stage1SafetyGates


class OperationalReadinessState(str, Enum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    APPROVED_CANDIDATE = "APPROVED_CANDIDATE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    ROLLED_BACK = "ROLLED_BACK"


class ApprovalLifecycleState(str, Enum):
    NOT_APPROVED = "NOT_APPROVED"
    APPROVED = "APPROVED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class OperationalApprovalRecord:
    approval_id: str
    approved_at: datetime
    expires_at: datetime
    operator: str
    source: str
    rollback_authority: str
    explicit_enable: bool = True
    revoked_at: datetime | None = None
    revoke_source: str | None = None

    def __post_init__(self) -> None:
        for name in ("approval_id", "operator", "source", "rollback_authority"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.expires_at <= self.approved_at:
            raise ValueError("expires_at must be after approved_at")
        if not self.explicit_enable:
            raise ValueError("explicit_enable is required")


@dataclass(frozen=True)
class OperationalAuditEvent:
    event_type: str
    timestamp: datetime
    source: str
    current_decision_owner: str
    candidate_owner: str
    execution_owner: str
    physical_owner: str
    transition_state: str
    reason: str


@dataclass(frozen=True)
class DecisionCutoverOperationalSnapshot:
    state: OperationalReadinessState
    transition_state: str
    current_decision_owner: str
    candidate_owner: str
    execution_owner: str
    physical_owner: str
    approval_state: ApprovalLifecycleState
    approval: OperationalApprovalRecord | None
    gates: Stage1SafetyGates
    missing_gates: tuple[str, ...]
    audit_trail: tuple[OperationalAuditEvent, ...]
    live_ownership_changed: bool = False


class DecisionCutoverOperationalReadinessModel:
    """Expose operational controls without enabling a live Stage 1 cutover."""

    def __init__(self) -> None:
        self._state = OperationalReadinessState.NOT_READY
        self._transition_state = "SHADOW_ONLY"
        self._current_decision_owner = "V2"
        self._candidate_owner = "V3"
        self._execution_owner = "V2"
        self._physical_owner = "V2"
        self._approval_state = ApprovalLifecycleState.NOT_APPROVED
        self._approval: OperationalApprovalRecord | None = None
        self._gates = Stage1SafetyGates(False, False, False, False, False)
        self._audit: list[OperationalAuditEvent] = []

    def evaluate_health(self, gates: Stage1SafetyGates, *, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        self._gates = gates
        self._approval = None
        self._approval_state = ApprovalLifecycleState.NOT_APPROVED
        self._state = OperationalReadinessState.READY if not gates.missing() else OperationalReadinessState.NOT_READY
        self._transition_state = "READY_FOR_STAGE1" if self._state is OperationalReadinessState.READY else "BLOCKED_BY_HEALTH_GATES"
        self._record("health_gates_evaluated", "health-gate-evaluation", "health gates evaluated", timestamp=timestamp)
        return self.snapshot()

    def approve(
        self,
        *,
        operator: str,
        source: str,
        rollback_authority: str,
        expires_at: datetime,
        timestamp: datetime | None = None,
    ) -> DecisionCutoverOperationalSnapshot:
        approved_at = timestamp or datetime.now(timezone.utc)
        if self._state is not OperationalReadinessState.READY:
            raise PermissionError("Stage 1 operational health gates are not satisfied")
        self._approval = OperationalApprovalRecord(
            uuid4().hex, approved_at, expires_at, operator, source, rollback_authority,
        )
        self._approval_state = ApprovalLifecycleState.APPROVED
        self._state = OperationalReadinessState.APPROVED_CANDIDATE
        self._transition_state = "APPROVED_CANDIDATE_SHADOW_ONLY"
        self._record("stage1_approval_recorded", source, "explicit approval recorded", timestamp=approved_at)
        return self.snapshot()

    def expire(self, *, timestamp: datetime | None = None, source: str = "approval-lifecycle") -> DecisionCutoverOperationalSnapshot:
        now = timestamp or datetime.now(timezone.utc)
        if self._approval is None or now < self._approval.expires_at:
            raise ValueError("approval has not expired")
        self._approval_state = ApprovalLifecycleState.EXPIRED
        self._state = OperationalReadinessState.EXPIRED
        self._transition_state = "EXPIRED_RETURN_TO_V2"
        self._record("stage1_approval_expired", source, "approval expiry", timestamp=now)
        return self.snapshot()

    def revoke(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        if self._approval is None:
            raise PermissionError("no approval to revoke")
        now = timestamp or datetime.now(timezone.utc)
        self._approval = replace(self._approval, revoked_at=now, revoke_source=source)
        self._approval_state = ApprovalLifecycleState.REVOKED
        self._state = OperationalReadinessState.REVOKED
        self._transition_state = "REVOKED_RETURN_TO_V2"
        self._record("stage1_approval_revoked", source, reason, timestamp=now)
        return self.snapshot()

    def emergency_rollback(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        now = timestamp or datetime.now(timezone.utc)
        self._current_decision_owner = "V2"
        self._approval_state = ApprovalLifecycleState.REVOKED if self._approval else ApprovalLifecycleState.NOT_APPROVED
        self._state = OperationalReadinessState.ROLLED_BACK
        self._transition_state = "EMERGENCY_ROLLBACK_TO_V2"
        self._record("emergency_decision_rollback", source, reason, timestamp=now)
        return self.snapshot()

    def disable_v3_decision(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        return self.emergency_rollback(source=source, reason=reason, timestamp=timestamp)

    def snapshot(self) -> DecisionCutoverOperationalSnapshot:
        return DecisionCutoverOperationalSnapshot(
            self._state, self._transition_state, self._current_decision_owner,
            self._candidate_owner, self._execution_owner, self._physical_owner,
            self._approval_state, self._approval, self._gates, self._gates.missing(),
            tuple(self._audit), False,
        )

    def _record(self, event_type: str, source: str, reason: str, *, timestamp: datetime | None = None) -> None:
        self._audit.append(OperationalAuditEvent(
            event_type, timestamp or datetime.now(timezone.utc), source,
            self._current_decision_owner, self._candidate_owner, self._execution_owner,
            self._physical_owner, self._transition_state, reason,
        ))


__all__ = [
    "OperationalReadinessState", "ApprovalLifecycleState", "OperationalApprovalRecord",
    "OperationalAuditEvent", "DecisionCutoverOperationalSnapshot",
    "DecisionCutoverOperationalReadinessModel",
]
