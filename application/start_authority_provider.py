"""Production authority binding for the fail-closed ACTIVE start policy."""

from __future__ import annotations

from datetime import datetime, timezone

from .decision_cutover_operational_readiness import (
    ApprovalLifecycleState,
    DecisionCutoverOperationalSnapshot,
    OperationalReadinessState,
)
from .start_activation_policy import StartActivationPolicy, StartExecutionMode


class StartAuthorityProvider:
    """Convert existing operational approval evidence into an ACTIVE policy.

    This provider creates no approval and performs no execution.  With no
    approved operational snapshot it deliberately returns the default-deny
    policy used by the production composition.
    """

    def __init__(self, *, now=None, expected_rollback_authority: str = "V2") -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._expected_rollback_authority = expected_rollback_authority

    def policy_from_snapshot(
        self,
        snapshot: DecisionCutoverOperationalSnapshot | None,
        *,
        bench_validation_passed: bool = False,
        rollback_validation_passed: bool = False,
        physical_gate_passed: bool = False,
    ) -> StartActivationPolicy:
        if snapshot is None or not self._approval_is_valid(snapshot):
            return StartActivationPolicy()

        gates = snapshot.gates
        if not (
            bench_validation_passed
            and rollback_validation_passed
            and physical_gate_passed
            and not gates.missing()
        ):
            return StartActivationPolicy()

        return StartActivationPolicy(
            execution_mode=StartExecutionMode.ACTIVE,
            explicit_active_enable=True,
            bench_validation_passed=True,
            rollback_validation_passed=True,
            physical_gate_passed=True,
        )

    def _approval_is_valid(self, snapshot: DecisionCutoverOperationalSnapshot) -> bool:
        approval = snapshot.approval
        if approval is None:
            return False
        if snapshot.state is not OperationalReadinessState.APPROVED_CANDIDATE:
            return False
        if snapshot.approval_state is not ApprovalLifecycleState.APPROVED:
            return False
        if approval.revoked_at is not None:
            return False
        if approval.rollback_authority != self._expected_rollback_authority:
            return False
        return self._now() < approval.expires_at


__all__ = ["StartAuthorityProvider"]
