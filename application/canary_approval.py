"""Non-authorizing Canary approval contract for readiness review."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class CanaryApprovalMode(str, Enum):
    OBSERVE_ONLY = "OBSERVE_ONLY"
    SHADOW_DECISION = "SHADOW_DECISION"
    APPROVED_CANARY = "APPROVED_CANARY"


@dataclass(frozen=True)
class CanaryApproval:
    approval_id: str
    mode: CanaryApprovalMode
    scope: str
    constraints: Mapping[str, str]
    approved_at: float
    expiry: float
    rollback_conditions: tuple[str, ...]
    revoked: bool = False

    def __post_init__(self) -> None:
        for name in ("approval_id", "scope"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.approved_at < 0 or self.expiry <= self.approved_at:
            raise ValueError("approval expiry must be after approval time")
        if not self.rollback_conditions:
            raise ValueError("rollback conditions are required")
        object.__setattr__(self, "constraints", MappingProxyType(dict(self.constraints)))

    def valid_at(self, now: float) -> bool:
        return not self.revoked and self.approved_at <= now < self.expiry

    def revoke(self) -> "CanaryApproval":
        return CanaryApproval(
            self.approval_id, self.mode, self.scope, self.constraints,
            self.approved_at, self.expiry, self.rollback_conditions, True,
        )


__all__ = ["CanaryApproval", "CanaryApprovalMode"]
