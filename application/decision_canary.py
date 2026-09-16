"""Bounded Stage 1 decision canary; execution ownership remains V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4


class CanaryState(str, Enum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    ACTIVE_DECISION = "ACTIVE_DECISION"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True)
class CanaryHealthSnapshot:
    safety_conflict: bool = False
    telemetry_healthy: bool = True
    configuration_conflict: bool = False
    runtime_failure: bool = False
    unexplained_divergence: bool = False

    def blockers(self) -> tuple[str, ...]:
        return tuple(name for name, blocked in (
            ("safety_conflict", self.safety_conflict),
            ("telemetry_unhealthy", not self.telemetry_healthy),
            ("configuration_conflict", self.configuration_conflict),
            ("runtime_failure", self.runtime_failure),
            ("unexplained_divergence", self.unexplained_divergence),
        ) if blocked)


@dataclass(frozen=True)
class CanaryApproval:
    approval_id: str
    approved_at: datetime
    operator: str
    source: str
    rollback_authority: str
    explicit_enable: bool = True

    def __post_init__(self) -> None:
        for name in ("approval_id", "operator", "source", "rollback_authority"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if not self.explicit_enable:
            raise ValueError("explicit_enable is required")


@dataclass(frozen=True)
class CanaryAuditEvent:
    event_type: str
    timestamp: datetime
    from_state: CanaryState
    to_state: CanaryState
    source: str
    reason: str
    scope: str


@dataclass(frozen=True)
class DecisionCanarySnapshot:
    state: CanaryState
    scope: str | None
    started_at: datetime | None
    expires_at: datetime | None
    approval: CanaryApproval | None
    rollback_policy: str
    health: CanaryHealthSnapshot
    blockers: tuple[str, ...]
    decision_owner: str
    execution_owner: str
    physical_owner: str
    audit_trail: tuple[CanaryAuditEvent, ...]
    live_execution_ownership_changed: bool = False


class DecisionCanaryController:
    """Control bounded decision authority only; never dispatches execution."""

    def __init__(self, *, rollback_policy: str = "AUTO_ROLLBACK_ON_BLOCKER_OR_EXPIRY") -> None:
        if not rollback_policy.strip():
            raise ValueError("rollback_policy is required")
        self._state = CanaryState.DISABLED
        self._scope: str | None = None
        self._started_at: datetime | None = None
        self._expires_at: datetime | None = None
        self._approval: CanaryApproval | None = None
        self._rollback_policy = rollback_policy
        self._health = CanaryHealthSnapshot()
        self._decision_owner = "V2"
        self._execution_owner = "V2"
        self._physical_owner = "V2"
        self._audit: list[CanaryAuditEvent] = []

    def enable_shadow(self, *, scope: str, source: str, timestamp: datetime | None = None) -> DecisionCanarySnapshot:
        if not scope.strip():
            raise ValueError("scope is required")
        self._transition(CanaryState.SHADOW, source, "shadow enabled", timestamp=timestamp, scope=scope)
        self._scope = scope
        return self.snapshot()

    def enter_canary(
        self,
        *,
        scope: str,
        duration: timedelta,
        operator: str,
        source: str,
        rollback_authority: str,
        health: CanaryHealthSnapshot,
        timestamp: datetime | None = None,
    ) -> DecisionCanarySnapshot:
        now = timestamp or datetime.now(timezone.utc)
        if self._state is not CanaryState.SHADOW:
            raise PermissionError("canary entry requires SHADOW state")
        if duration <= timedelta(0):
            raise ValueError("duration must be positive")
        if health.blockers():
            self._health = health
            self._transition(CanaryState.ROLLBACK, source, "canary blocked by health", timestamp=now, scope=scope)
            return self.snapshot()
        self._scope = scope
        self._started_at = now
        self._expires_at = now + duration
        self._approval = CanaryApproval(uuid4().hex, now, operator, source, rollback_authority)
        self._health = health
        self._decision_owner = "V3"
        self._transition(CanaryState.CANARY, source, "bounded canary enabled", timestamp=now, scope=scope)
        return self.snapshot()

    def activate_decision(self, *, source: str, timestamp: datetime | None = None) -> DecisionCanarySnapshot:
        if self._state is not CanaryState.CANARY:
            raise PermissionError("ACTIVE_DECISION requires CANARY state")
        self._transition(CanaryState.ACTIVE_DECISION, source, "decision authority activated", timestamp=timestamp)
        return self.snapshot()

    def observe_health(self, health: CanaryHealthSnapshot, *, source: str, timestamp: datetime | None = None) -> DecisionCanarySnapshot:
        self._health = health
        if health.blockers() and self._state in {CanaryState.CANARY, CanaryState.ACTIVE_DECISION}:
            return self.rollback(source=source, reason=";".join(health.blockers()), timestamp=timestamp)
        return self.snapshot()

    def tick(self, *, timestamp: datetime | None = None, source: str = "canary-clock") -> DecisionCanarySnapshot:
        now = timestamp or datetime.now(timezone.utc)
        if self._expires_at is not None and now >= self._expires_at and self._state in {CanaryState.CANARY, CanaryState.ACTIVE_DECISION}:
            return self.rollback(source=source, reason="canary_expired", timestamp=now)
        return self.snapshot()

    def rollback(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCanarySnapshot:
        self._decision_owner = "V2"
        self._transition(CanaryState.ROLLBACK, source, reason, timestamp=timestamp)
        return self.snapshot()

    def disable(self, *, source: str, timestamp: datetime | None = None) -> DecisionCanarySnapshot:
        self._decision_owner = "V2"
        self._transition(CanaryState.DISABLED, source, "canary disabled", timestamp=timestamp)
        return self.snapshot()

    def snapshot(self) -> DecisionCanarySnapshot:
        return DecisionCanarySnapshot(
            self._state, self._scope, self._started_at, self._expires_at,
            self._approval, self._rollback_policy, self._health,
            self._health.blockers(), self._decision_owner, self._execution_owner,
            self._physical_owner, tuple(self._audit), False,
        )

    def _transition(
        self,
        state: CanaryState,
        source: str,
        reason: str,
        *,
        timestamp: datetime | None = None,
        scope: str | None = None,
    ) -> None:
        previous = self._state
        self._state = state
        effective_scope = scope or self._scope or "unspecified"
        self._audit.append(CanaryAuditEvent(
            f"canary_{state.value.lower()}", timestamp or datetime.now(timezone.utc),
            previous, state, source, reason, effective_scope,
        ))


__all__ = [
    "CanaryState", "CanaryHealthSnapshot", "CanaryApproval", "CanaryAuditEvent",
    "DecisionCanarySnapshot", "DecisionCanaryController",
]
