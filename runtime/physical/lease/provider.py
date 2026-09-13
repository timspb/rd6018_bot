from __future__ import annotations

from time import time
from uuid import uuid4

from .audit import LeaseAudit, LeaseAuditRecord
from .models import BenchExecutionLease, BenchLeaseScope, BenchLeaseStatus
from .validation import validate_lease


class BenchLeaseProvider:
    """Manual, bench-only authorization; never a production authority."""

    def __init__(self, *, duration_s: float = 300.0, clock=time, audit: LeaseAudit | None = None):
        if duration_s <= 0:
            raise ValueError("bench lease duration must be positive")
        self.duration_s = duration_s
        self.clock = clock
        self.audit = audit or LeaseAudit()
        self._leases: dict[str, BenchExecutionLease] = {}

    def request(self, operator: str, scope: BenchLeaseScope) -> BenchExecutionLease:
        operator = operator.strip()
        if not operator:
            self.audit.record(lease_id=None, operator="", scope=str(scope), action="request", result="REJECTED", reason="operator_required")
            raise ValueError("operator is required")
        if scope is not BenchLeaseScope.DISABLE_OUTPUT_ONLY:
            self.audit.record(lease_id=None, operator=operator, scope=str(scope), action="request", result="REJECTED", reason="scope_not_allowed")
            raise ValueError("bench scope is not allowed")
        now = self.clock()
        lease = BenchExecutionLease(str(uuid4()), operator, now, now + self.duration_s, scope)
        self._leases[lease.lease_id] = lease
        self.audit.record(lease_id=lease.lease_id, operator=operator, scope=scope.value, action="request", result="ACCEPTED", reason="manual_bench_lease")
        return lease

    def validate(self, lease: BenchExecutionLease | None, scope: BenchLeaseScope = BenchLeaseScope.DISABLE_OUTPUT_ONLY) -> bool:
        valid, reason = validate_lease(lease, scope, now=self.clock())
        if not valid and lease is not None and lease.status is BenchLeaseStatus.ACTIVE and self.clock() >= lease.expires_at:
            lease.status = BenchLeaseStatus.EXPIRED
        self.audit.record(lease_id=lease.lease_id if lease else None, operator=lease.operator if lease else "", scope=scope.value, action="validate", result="ACCEPTED" if valid else "REJECTED", reason=reason)
        return valid

    def revoke(self, lease: BenchExecutionLease) -> LeaseAuditRecord:
        lease.status = BenchLeaseStatus.REVOKED
        return self.audit.record(lease_id=lease.lease_id, operator=lease.operator, scope=lease.scope.value, action="revoke", result="ACCEPTED", reason="operator_revoke")

    def expire(self) -> tuple[str, ...]:
        now = self.clock()
        expired = []
        for lease in self._leases.values():
            if lease.status is BenchLeaseStatus.ACTIVE and now >= lease.expires_at:
                lease.status = BenchLeaseStatus.EXPIRED
                expired.append(lease.lease_id)
                self.audit.record(lease_id=lease.lease_id, operator=lease.operator, scope=lease.scope.value, action="expire", result="EXPIRED", reason="lease_timeout")
        return tuple(expired)
