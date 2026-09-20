"""Operator-facing authority lifecycle for the gated V3 ACTIVE path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .decision_cutover_operational_readiness import DecisionCutoverOperationalSnapshot
from .decision_cutover_readiness import Stage1SafetyGates
from .start_authority_runtime import AuthorityWindow, StartAuthorityRuntime


@dataclass(frozen=True)
class OperatorApprovalResult:
    accepted: bool
    reason: str
    snapshot: DecisionCutoverOperationalSnapshot
    window: AuthorityWindow | None


class OperatorAuthorityInterface:
    """Application boundary for approval/revocation only; never executes hardware."""

    def __init__(self, runtime: StartAuthorityRuntime) -> None:
        self.runtime = runtime

    def update_evidence(
        self,
        gates: Stage1SafetyGates,
        *,
        bench_validation_passed: bool,
        rollback_validation_passed: bool,
        physical_gate_passed: bool,
        timestamp: datetime | None = None,
    ) -> DecisionCutoverOperationalSnapshot:
        return self.runtime.update_evidence(
            gates,
            bench_validation_passed=bench_validation_passed,
            rollback_validation_passed=rollback_validation_passed,
            physical_gate_passed=physical_gate_passed,
            timestamp=timestamp,
        )

    def approve(
        self,
        *,
        operator: str,
        source: str,
        scope: str,
        expires_in: timedelta,
        rollback_authority: str = "V2",
        correlation_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> OperatorApprovalResult:
        now = timestamp or datetime.now(timezone.utc)
        if expires_in <= timedelta(0):
            return OperatorApprovalResult(False, "invalid_expiry", self.runtime.snapshot(), None)
        try:
            snapshot = self.runtime.approve(
                operator=operator,
                source=source,
                scope=scope,
                correlation_id=correlation_id or uuid4().hex,
                rollback_authority=rollback_authority,
                expires_at=now + expires_in,
                timestamp=now,
            )
        except (PermissionError, ValueError) as exc:
            return OperatorApprovalResult(False, str(exc), self.runtime.snapshot(), None)
        return OperatorApprovalResult(True, "authority_approved", snapshot, self.runtime.authority_window)

    def revoke(self, *, source: str, reason: str, timestamp: datetime | None = None) -> DecisionCutoverOperationalSnapshot:
        return self.runtime.revoke(source=source, reason=reason, timestamp=timestamp)

    def snapshot(self) -> DecisionCutoverOperationalSnapshot:
        return self.runtime.snapshot()


__all__ = ["OperatorApprovalResult", "OperatorAuthorityInterface"]
