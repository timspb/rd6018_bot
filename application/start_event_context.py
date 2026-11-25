"""Immutable, non-runtime context passed across the preserved production START boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from types import SimpleNamespace
from typing import Any, Mapping

from application.execution_intent.models import ExecutionIntent, SafetyContext


def build_start_execution_identity(
    *, event_context: Any, recovery_context: Any, battery_id: Any, mode: str
) -> Any:
    """Map START trace/session data into the identity used by ExecutionPort."""
    if not isinstance(recovery_context, dict):
        recovery_context = {}
    trace_id = str(getattr(event_context, "trace_id", "") or "")
    session_id = str(recovery_context.get("session_id") or "")
    if not session_id:
        session_id = f"{mode.lower()}:{battery_id}"
    if not trace_id:
        trace_id = f"{mode.lower()}:{session_id}"
    return SimpleNamespace(session_id=session_id, trace_id=trace_id)


def build_start_execution_intent(
    *, voltage_v: float, current_a: float, mode: str, identity: Any,
    limits_reference: str,
) -> ExecutionIntent:
    """Build the START data contract without reading runtime/controller state."""
    return ExecutionIntent(
        requested_voltage_v=float(voltage_v),
        requested_current_a=float(current_a),
        requested_mode=mode,
        source_decision_id=f"{mode.lower()}:{identity.trace_id}",
        safety_context=SafetyContext(
            telemetry_state="FRESH",
            lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED",
            limits_reference=limits_reference,
        ),
    )


@dataclass(frozen=True)
class StartEventContext:
    """Data-only context; it is not a Telegram event or a runtime handle."""

    trace_id: str
    actor: str
    source: str
    intent_metadata: Mapping[str, Any] = field(default_factory=dict)
    profile: str = ""
    capacity_ah: float = 0.0
    condition: Any = None
    correlation_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id is required")
        object.__setattr__(self, "intent_metadata", MappingProxyType(dict(self.intent_metadata)))
        object.__setattr__(self, "correlation_metadata", MappingProxyType(dict(self.correlation_metadata)))
