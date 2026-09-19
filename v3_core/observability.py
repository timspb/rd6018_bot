"""Pure V3 operator observability contracts with no side effects."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


class DiagnosticCategory(str, Enum):
    DOMAIN = "DOMAIN"
    SAFETY = "SAFETY"
    EXECUTION = "EXECUTION"
    TRANSPORT = "TRANSPORT"
    CONFIGURATION = "CONFIGURATION"
    PERSISTENCE = "PERSISTENCE"
    UI = "UI"
    OPERATOR = "OPERATOR"


class DiagnosticSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    WARNING = "WARNING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TraceContext:
    session_id: str
    trace_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.session_id, self.trace_id, self.correlation_id)):
            raise ValueError("session, trace and correlation ids are required")

    @classmethod
    def create(cls, session_id: str) -> "TraceContext":
        return cls(session_id, uuid4().hex, uuid4().hex)

    def child(self) -> "TraceContext":
        return TraceContext(self.session_id, self.trace_id, uuid4().hex)


@dataclass(frozen=True)
class DiagnosticEvent:
    event_id: str
    timestamp: datetime
    severity: DiagnosticSeverity
    category: DiagnosticCategory
    source: str
    component: str
    message: str
    trace_id: str
    session_id: str
    correlation_id: str
    state_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.event_id, self.source, self.component, self.message, self.trace_id, self.session_id, self.correlation_id)):
            raise ValueError("diagnostic identity and message are required")


class DiagnosticsDomain:
    """In-memory live diagnostic source; no logging, UI or persistence calls."""

    def __init__(self) -> None:
        self._events: list[DiagnosticEvent] = []

    def emit(self, *, context: TraceContext, severity: DiagnosticSeverity, category: DiagnosticCategory, source: str, component: str, message: str, state_context: Mapping[str, Any] | None = None, timestamp: datetime | None = None) -> DiagnosticEvent:
        event = DiagnosticEvent(uuid4().hex, timestamp or datetime.now(timezone.utc), severity, category, source, component, message, context.trace_id, context.session_id, context.correlation_id, dict(state_context or {}))
        self._events.append(event)
        return event

    def snapshot(self, *, limit: int = 50) -> tuple[DiagnosticEvent, ...]:
        if limit < 0:
            raise ValueError("limit cannot be negative")
        return tuple(self._events[-limit:] if limit else ())


@dataclass(frozen=True)
class SystemHealthSnapshot:
    runtime: HealthStatus
    domain: HealthStatus
    safety: HealthStatus
    execution: HealthStatus
    transport: HealthStatus
    configuration: HealthStatus
    persistence: HealthStatus
    ui: HealthStatus
    workers: tuple[str, ...] = ()
    lifecycle: str = "UNKNOWN"
    composition: str = "UNKNOWN"
    active_containment: str | None = None
    last_execution_result: str | None = None
    unresolved_configuration: tuple[str, ...] = ()
    storage_status: str = "UNKNOWN"

    @property
    def overall(self) -> HealthStatus:
        statuses = (self.runtime, self.domain, self.safety, self.execution, self.transport, self.configuration, self.persistence, self.ui)
        if HealthStatus.FAILED in statuses:
            return HealthStatus.FAILED
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY


@dataclass(frozen=True)
class OperatorAlert:
    alert_id: str
    severity: DiagnosticSeverity
    source: str
    timestamp: datetime
    description: str
    affected_component: str
    recommended_action: str
    resolved: bool = False

    def resolve(self) -> "OperatorAlert":
        return replace(self, resolved=True)


@dataclass(frozen=True)
class OperatorDashboardSnapshot:
    current_charge: Mapping[str, Any]
    recent_timeline: tuple[Any, ...]
    health: SystemHealthSnapshot
    safety_state: str
    execution_state: Mapping[str, Any]
    configuration: Mapping[str, Any]
    diagnostics: tuple[DiagnosticEvent, ...]
    alerts: tuple[OperatorAlert, ...]
    shadow_status: Mapping[str, Any] | None = None
    canary_readiness: Mapping[str, Any] | None = None
    canary_preflight: Mapping[str, Any] | None = None
    live_canary_preflight: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DiagnosticHistoryQuery:
    session_id: str | None = None
    category: DiagnosticCategory | None = None
    minimum_severity: DiagnosticSeverity | None = None
    limit: int = 100


class DiagnosticHistory:
    """Read-only query contract over supplied events; persistence is external."""

    def query(self, events: tuple[DiagnosticEvent, ...], query: DiagnosticHistoryQuery) -> tuple[DiagnosticEvent, ...]:
        if query.limit < 0:
            raise ValueError("limit cannot be negative")
        severity_order = {severity: index for index, severity in enumerate(DiagnosticSeverity)}
        result = [event for event in events if (query.session_id is None or event.session_id == query.session_id) and (query.category is None or event.category is query.category) and (query.minimum_severity is None or severity_order[event.severity] >= severity_order[query.minimum_severity])]
        return tuple(result[-query.limit:] if query.limit else ())


__all__ = [
    "DiagnosticCategory", "DiagnosticSeverity", "HealthStatus", "TraceContext", "DiagnosticEvent",
    "DiagnosticsDomain", "SystemHealthSnapshot", "OperatorAlert", "OperatorDashboardSnapshot",
    "DiagnosticHistoryQuery", "DiagnosticHistory",
]
