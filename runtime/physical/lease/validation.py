from __future__ import annotations

from time import time

from .models import BenchExecutionLease, BenchLeaseScope, BenchLeaseStatus


def validate_lease(lease: BenchExecutionLease | None, scope: BenchLeaseScope,
                   *, now: float | None = None) -> tuple[bool, str]:
    if lease is None:
        return False, "bench_lease_required"
    if not lease.operator.strip():
        return False, "operator_required"
    if lease.scope is not scope:
        return False, "lease_scope_mismatch"
    current = time() if now is None else now
    if lease.status is not BenchLeaseStatus.ACTIVE:
        return False, f"lease_{lease.status.value}"
    if current >= lease.expires_at:
        return False, "lease_expired"
    return True, "lease_valid"
