from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BenchLeaseScope(str, Enum):
    DISABLE_OUTPUT_ONLY = "DISABLE_OUTPUT_ONLY"


class BenchLeaseStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class BenchExecutionLease:
    lease_id: str
    operator: str
    created_at: float
    expires_at: float
    scope: BenchLeaseScope
    status: BenchLeaseStatus = BenchLeaseStatus.ACTIVE
