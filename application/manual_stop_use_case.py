"""Application orchestration for stopping an existing Manual session."""

from __future__ import annotations

from application.execution_intent.models import ExecutionIntent, SafetyContext
from v3_core.canonical_events import EventType


async def stop_manual_session(session, reason="operator_stop") -> bool:
    self = session
    self.stop_reason = str(reason)
    confirmed = False
    try:
        stop_intent = ExecutionIntent(
            requested_voltage_v=0.0,
            requested_current_a=0.0,
            requested_mode="MANUAL_STOP",
            source_decision_id=f"manual_stop:{self.identity_integration.identity.trace_id if self.identity_integration.identity else 'legacy'}",
            safety_context=SafetyContext(verification_state="REQUIRED", lease_state="V2_PHYSICAL_OWNER"),
        )
        confirmed = (await self.execution_port.disable(
            stop_intent,
            identity=self.identity_integration.identity,
            reason=self.stop_reason,
        )).verified
    finally:
        self._transition_state(
            type(self.state).STOPPED if confirmed else type(self.state).FAILED,
            self.stop_reason,
        )
        self.cooling_started_at = None
        self._persist()
        if self.identity_integration.identity is not None:
            self.identity_integration.emit(
                event_type=EventType.SESSION_STOPPED,
                phase_before=type(self.state).ACTIVE.value,
                phase_after=self.state.value,
                reason=self.stop_reason,
            )
    return confirmed


__all__ = ["stop_manual_session"]
