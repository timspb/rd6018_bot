"""Data-only START authority contracts for the future V3 flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


class Mode(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class InitialState(str, Enum):
    IDLE = "IDLE"
    ARMING = "ARMING"


class StartDecisionStatus(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class StartRequest:
    """Operator intent accepted as data; it does not start anything."""

    operator_intent: Any
    program_id: str
    battery_identity: str
    mode: Mode
    requested_parameters_ref: str
    requested_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("program_id", "battery_identity", "requested_parameters_ref"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.mode, Mode):
            raise TypeError("mode must be Mode.AUTO or Mode.MANUAL")
        object.__setattr__(self, "requested_parameters", MappingProxyType(dict(self.requested_parameters)))


@dataclass(frozen=True)
class StartIdentity:
    """Identity is created before lifecycle START and is transport-independent."""

    session_id: str
    trace_id: str
    graph_session_id: str
    created_at: float

    @classmethod
    def create(cls, *, created_at: float | None = None) -> "StartIdentity":
        return cls(uuid4().hex, uuid4().hex, uuid4().hex, float(time() if created_at is None else created_at))

    def __post_init__(self) -> None:
        for name in ("session_id", "trace_id", "graph_session_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.created_at < 0:
            raise ValueError("created_at cannot be negative")


@dataclass(frozen=True)
class SessionStarted:
    """Lifecycle fact only; it does not assert that physical Output is ON."""

    identity: StartIdentity
    timestamp: float
    program_id: str
    initial_state: InitialState = InitialState.ARMING

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError("timestamp cannot be negative")
        if not str(self.program_id).strip():
            raise ValueError("program_id is required")


@dataclass(frozen=True)
class StartDecision:
    status: StartDecisionStatus
    reason: str
    identity: StartIdentity | None = None
    lifecycle_event: SessionStarted | None = None

    def __post_init__(self) -> None:
        if not str(self.reason).strip():
            raise ValueError("reason is required")
        if self.status is StartDecisionStatus.ALLOW and (self.identity is None or self.lifecycle_event is None):
            raise ValueError("ALLOW requires identity and SessionStarted event")
        if self.status is not StartDecisionStatus.ALLOW and self.lifecycle_event is not None:
            raise ValueError("DENY/AMBIGUOUS cannot emit SessionStarted")


@dataclass(frozen=True)
class PhysicalVerification:
    """Result supplied later by execution boundary; this contract performs no I/O."""

    verified: bool
    output_on: bool | None
    timestamp: float
    reason: str

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError("timestamp cannot be negative")
        if not str(self.reason).strip():
            raise ValueError("reason is required")


__all__ = [
    "InitialState", "Mode", "PhysicalVerification", "SessionStarted",
    "StartDecision", "StartDecisionStatus", "StartIdentity", "StartRequest",
]
