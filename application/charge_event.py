"""Data-only Phase 2 charge event contract.

This module intentionally has no journal, Telegram, HA, controller, or physical
dependencies. Production writers are not connected by this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ChargeEvent:
    """Immutable, transport-independent event envelope."""

    event_id: str
    trace_id: str
    session_id: str
    timestamp: float
    source: str
    event_type: str
    severity: str
    profile: str | None = None
    phase: str | None = None
    measurements: Mapping[str, Any] = field(default_factory=dict)
    decision: Mapping[str, Any] = field(default_factory=dict)
    actuator_effect: Mapping[str, Any] = field(default_factory=dict)
    failure_state: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("event_id", "trace_id", "session_id", "source", "event_type", "severity"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        if not isinstance(self.timestamp, (int, float)) or not isfinite(float(self.timestamp)):
            raise ValueError("timestamp must be a finite number")
        for field_name in ("measurements", "decision", "actuator_effect"):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{field_name} must be a mapping")
            object.__setattr__(self, field_name, _freeze(value))
        for field_name in ("profile", "phase", "failure_state"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")

    @classmethod
    def new(
        cls,
        *,
        trace_id: str,
        session_id: str,
        source: str,
        event_type: str,
        severity: str,
        timestamp: float | None = None,
        **kwargs: Any,
    ) -> "ChargeEvent":
        return cls(
            event_id=uuid4().hex,
            trace_id=trace_id,
            session_id=session_id,
            timestamp=(datetime.now(timezone.utc).timestamp() if timestamp is None else timestamp),
            source=source,
            event_type=event_type,
            severity=severity,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "event_type": self.event_type,
            "severity": self.severity,
            "profile": self.profile,
            "phase": self.phase,
            "measurements": _plain(self.measurements),
            "decision": _plain(self.decision),
            "actuator_effect": _plain(self.actuator_effect),
            "failure_state": self.failure_state,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChargeEvent":
        required = {"event_id", "trace_id", "session_id", "timestamp", "source", "event_type", "severity"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError("missing ChargeEvent fields: " + ", ".join(missing))
        return cls(**{field: payload.get(field) for field in cls.__dataclass_fields__})

