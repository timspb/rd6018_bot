"""Pure diagnostics and observability contracts for Phase 6.5.

This module records facts and correlation metadata only.  It does not decide
safety or charging outcomes and has no transport, UI, persistence, or physical
dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


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


class DiagnosticCategory(str, Enum):
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    OPERATOR = "operator"


class DiagnosticSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class TraceCorrelation:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trace_id.strip() or not self.span_id.strip():
            raise ValueError("trace_id and span_id are required")


@dataclass(frozen=True)
class DiagnosticEvent:
    """Immutable fact envelope for domain, infrastructure, or operator events."""

    event_id: str
    timestamp: float
    category: DiagnosticCategory
    event_type: str
    severity: DiagnosticSeverity
    correlation: TraceCorrelation
    source: str
    payload: Mapping[str, Any] = MappingProxyType({})
    error_code: str | None = None
    warning_code: str | None = None
    audit_action: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.event_type.strip() or not self.source.strip():
            raise ValueError("event_id, event_type and source are required")
        if not isinstance(self.category, DiagnosticCategory):
            raise TypeError("category must be DiagnosticCategory")
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be DiagnosticSeverity")
        if not isinstance(self.timestamp, (int, float)) or not isfinite(float(self.timestamp)):
            raise ValueError("timestamp must be finite")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", _freeze(self.payload))

    @classmethod
    def new(
        cls,
        *,
        category: DiagnosticCategory,
        event_type: str,
        severity: DiagnosticSeverity,
        correlation: TraceCorrelation,
        source: str,
        timestamp: float | None = None,
        payload: Mapping[str, Any] | None = None,
        error_code: str | None = None,
        warning_code: str | None = None,
        audit_action: str | None = None,
    ) -> "DiagnosticEvent":
        return cls(
            event_id=uuid4().hex,
            timestamp=datetime.now(timezone.utc).timestamp() if timestamp is None else timestamp,
            category=category,
            event_type=event_type,
            severity=severity,
            correlation=correlation,
            source=source,
            payload=payload or {},
            error_code=error_code,
            warning_code=warning_code,
            audit_action=audit_action,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "category": self.category.value,
            "event_type": self.event_type,
            "severity": self.severity.value,
            "correlation": {
                "trace_id": self.correlation.trace_id,
                "span_id": self.correlation.span_id,
                "parent_span_id": self.correlation.parent_span_id,
                "session_id": self.correlation.session_id,
            },
            "source": self.source,
            "payload": _plain(self.payload),
            "error_code": self.error_code,
            "warning_code": self.warning_code,
            "audit_action": self.audit_action,
        }


class DiagnosticsDomain:
    """Factory boundary; it returns records and performs no side effects."""

    def event(self, **kwargs: Any) -> DiagnosticEvent:
        return DiagnosticEvent.new(**kwargs)


__all__ = [
    "DiagnosticCategory", "DiagnosticSeverity", "TraceCorrelation",
    "DiagnosticEvent", "DiagnosticsDomain",
]
