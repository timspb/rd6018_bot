"""Application orchestration for starting an existing Manual session."""

from __future__ import annotations

import asyncio
import time

from application.execution_intent.models import ExecutionIntent, SafetyContext
from v3_core.canonical_events import EventType


async def start_manual_session(session, request, *, max_manual_voltage) -> bool:
    self = session
    if self.is_active:
        raise RuntimeError("manual session is already active")
    if bool(getattr(self.app.charge_controller, "is_active", False)):
        raise RuntimeError("automatic charge controller is active")

    self.request = request
    self.identity_integration.create_for_start(
        profile=request.battery_id or request.operation_mode,
        source="manual",
        created_at=time.time(),
    )
    self._manual_start_event_emitted = False
    self._transition_state(type(self.state).ARMING, "operator_start")
    self.started_at = time.time()
    self.paused_total_s = 0.0
    self.cooling_started_at = None
    self.stop_reason = ""
    self.phase_transition_reason = ""
    self.phase_lifecycle.reset()
    self._reset_delta_tracking()
    self.main_min_confirmations = 0
    self.main_min_hold_started_at = None
    self._last_main_min_confirmation = 0.0
    self.finish_hold_started_at = None
    self._persist()

    start_intent = ExecutionIntent(
        requested_voltage_v=request.voltage_v,
        requested_current_a=request.current_a,
        requested_mode="MANUAL_START",
        source_decision_id=f"manual_start:{self.identity_integration.identity.trace_id}",
        safety_context=SafetyContext(
            telemetry_state="FRESH",
            lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED",
            limits_reference="existing V2 guarded setter policy",
        ),
    )
    result = await self.execution_port.enable(
        start_intent,
        identity=self.identity_integration.identity,
        recipe_voltage_ceiling_v=float(max_manual_voltage),
    )
    if not result.verified:
        self.stop_reason = result.reason or "safe_enable_failed"
        self._transition_state(type(self.state).FAILED, self.stop_reason)
        self._persist()
        return False

    self._transition_state(type(self.state).ACTIVE, "safe_enable_confirmed")
    self.identity_integration.emit(
        event_type=EventType.SESSION_STARTED,
        phase_before=type(self.state).ARMING.value,
        phase_after=type(self.state).ACTIVE.value,
        reason="safe_enable_confirmed",
    )
    self._manual_start_event_emitted = True
    self._persist()
    self._task = asyncio.create_task(self._run(), name="rd6018-manual-session")
    return True


__all__ = ["start_manual_session"]
