"""Contract-only identity bridge for the existing V2 execution boundary.

This module carries correlation metadata; it does not call a transport, mutate
V2 state, or create identities for legacy operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class IdentityPropagationStatus(str, Enum):
    PROPAGATED = "PROPAGATED"
    UNKNOWN_LEGACY_NO_IDENTITY = "UNKNOWN_LEGACY_NO_IDENTITY"
    BLOCKED_PARTIAL_IDENTITY = "BLOCKED_PARTIAL_IDENTITY"


class V2Operation(str, Enum):
    START = "START"
    STOP = "STOP"
    SETTINGS = "SETTINGS"


@dataclass(frozen=True)
class ExecutionIdentityEnvelope:
    session_id: str | None
    trace_id: str | None
    decision_id: str | None
    intent_id: str | None
    status: IdentityPropagationStatus

    @classmethod
    def from_v3(
        cls,
        *,
        session_id: str | None,
        trace_id: str | None,
        decision_id: str | None,
        intent_id: str | None,
    ) -> "ExecutionIdentityEnvelope":
        values = (session_id, trace_id, decision_id, intent_id)
        present = [bool(str(value).strip()) if value is not None else False for value in values]
        if all(present):
            return cls(session_id, trace_id, decision_id, intent_id, IdentityPropagationStatus.PROPAGATED)
        if not any(present):
            return cls(None, None, None, None, IdentityPropagationStatus.UNKNOWN_LEGACY_NO_IDENTITY)
        return cls(session_id, trace_id, decision_id, intent_id, IdentityPropagationStatus.BLOCKED_PARTIAL_IDENTITY)

    @property
    def correlated(self) -> bool:
        return self.status is IdentityPropagationStatus.PROPAGATED


@dataclass(frozen=True)
class V2ExecutionBoundaryRequest:
    operation: V2Operation | str
    parameters: Mapping[str, Any]
    identity: ExecutionIdentityEnvelope

    def __post_init__(self) -> None:
        operation = self.operation if isinstance(self.operation, V2Operation) else V2Operation(str(self.operation))
        object.__setattr__(self, "operation", operation)
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")


@dataclass(frozen=True)
class AuditCorrelation:
    operation: V2Operation
    identity: ExecutionIdentityEnvelope
    result: str
    reason: str


def bridge_request(
    operation: V2Operation | str,
    *,
    parameters: Mapping[str, Any] | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    decision_id: str | None = None,
    intent_id: str | None = None,
) -> V2ExecutionBoundaryRequest:
    """Build metadata for V2 without invoking the V2 executor."""

    identity = ExecutionIdentityEnvelope.from_v3(
        session_id=session_id,
        trace_id=trace_id,
        decision_id=decision_id,
        intent_id=intent_id,
    )
    return V2ExecutionBoundaryRequest(operation, dict(parameters or {}), identity)


__all__ = [
    "AuditCorrelation",
    "ExecutionIdentityEnvelope",
    "IdentityPropagationStatus",
    "V2ExecutionBoundaryRequest",
    "V2Operation",
    "bridge_request",
]
