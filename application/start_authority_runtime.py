"""Runtime-owned, bounded authority lifecycle for controlled ACTIVE starts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .decision_cutover_operational_readiness import (
    DecisionCutoverOperationalReadinessModel,
    DecisionCutoverOperationalSnapshot,
)
from .decision_cutover_readiness import Stage1SafetyGates


@dataclass(frozen=True)
class AuthorityWindow:
    approval_id: str
    operator: str
    source: str
    scope: str
    correlation_id: str
    approved_at: datetime
    expires_at: datetime
    rollback_authority: str


class StartAuthorityRuntime:
    """Own approval/readiness state without owning execution or hardware."""

    def __init__(self) -> None:
        self._model = DecisionCutoverOperationalReadinessModel()
        self._bench_validation_passed = False
        self._rollback_validation_passed = False
        self._physical_gate_passed = False
        self._window: AuthorityWindow | None = None

    @property
    def bench_validation_passed(self) -> bool:
        return self._bench_validation_passed

    @property
    def rollback_validation_passed(self) -> bool:
        return self._rollback_validation_passed

    @property
    def gate_physical_passed(self) -> bool:
        return self._physical_gate_passed

    @property
    def authority_window(self) -> AuthorityWindow | None:
        return self._window

    def update_evidence(
        self,
        gates: Stage1SafetyGates,
        *,
        bench_validation_passed: bool,
        rollback_validation_passed: bool,
        physical_gate_passed: bool,
        timestamp: datetime | None = None,
    ) -> DecisionCutoverOperationalSnapshot:
        self._bench_validation_passed = bench_validation_passed
        self._rollback_validation_passed = rollback_validation_passed
        self._physical_gate_passed = physical_gate_passed
        self._window = None
        return self._model.evaluate_health(gates, timestamp=timestamp)

    def approve(
        self,
        *,
        operator: str,
        source: str,
        scope: str,
        correlation_id: str,
        rollback_authority: str,
        expires_at: datetime,
        timestamp: datetime | None = None,
    ) -> DecisionCutoverOperationalSnapshot:
        for name, value in (
            ("operator", operator), ("source", source), ("scope", scope),
            ("correlation_id", correlation_id), ("rollback_authority", rollback_authority),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        approved_at = timestamp or datetime.now(timezone.utc)
        snapshot = self._model.approve(
            operator=operator,
            source=source,
            rollback_authority=rollback_authority,
            expires_at=expires_at,
            timestamp=approved_at,
        )
        assert snapshot.approval is not None
        self._window = AuthorityWindow(
            snapshot.approval.approval_id, operator, source, scope, correlation_id,
            approved_at, expires_at, rollback_authority,
        )
        return snapshot

    def snapshot(self) -> DecisionCutoverOperationalSnapshot:
        return self._model.snapshot()

    def revoke(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        self._window = None
        return self._model.revoke(source=source, reason=reason, timestamp=timestamp)

    def rollback(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        self._window = None
        return self._model.emergency_rollback(source=source, reason=reason, timestamp=timestamp)

    def expire(self, *, timestamp: datetime | None = None, source: str = "authority-lifecycle") -> DecisionCutoverOperationalSnapshot:
        self._window = None
        return self._model.expire(timestamp=timestamp, source=source)


__all__ = ["AuthorityWindow", "StartAuthorityRuntime"]
