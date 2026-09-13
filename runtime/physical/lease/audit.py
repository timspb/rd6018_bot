from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class LeaseAuditRecord:
    timestamp: float
    lease_id: str | None
    operator: str
    scope: str
    action: str
    result: str
    reason: str


class LeaseAudit:
    def __init__(self) -> None:
        self.records: list[LeaseAuditRecord] = []

    def record(self, *, lease_id: str | None, operator: str, scope: str,
               action: str, result: str, reason: str) -> LeaseAuditRecord:
        record = LeaseAuditRecord(time(), lease_id, operator, scope, action, result, reason)
        self.records.append(record)
        return record
