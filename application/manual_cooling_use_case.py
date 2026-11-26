"""Manual-session cooling entry and resume application workflows."""

import time

from application.execution_intent.models import ExecutionIntent, SafetyContext


async def enter_manual_cooling(session) -> None:
    self = session
    if self.state is type(self.state).COOLING:
        return
    stop_intent = ExecutionIntent(
        requested_voltage_v=0.0,
        requested_current_a=0.0,
        requested_mode="MANUAL_COOLING_STOP",
        source_decision_id=f"manual_cooling:{self.identity_integration.identity.trace_id if self.identity_integration.identity else 'legacy'}",
        safety_context=SafetyContext(verification_state="REQUIRED", lease_state="V2_PHYSICAL_OWNER"),
    )
    if not (await self.execution_port.disable(stop_intent, identity=self.identity_integration.identity, reason="thermal_pause")).verified:
        self.stop_reason = "cooling_output_off_unconfirmed"
        self._transition_state(type(self.state).FAILED, self.stop_reason)
        self._persist()
        return
    self._transition_state(type(self.state).COOLING, "thermal_pause")
    self.cooling_started_at = time.time()
    self._reset_delta_tracking()
    self.finish_hold_started_at = None
    self._persist()


async def resume_manual_after_cooling(session, *, max_manual_voltage) -> None:
    self = session
    if self.state is not type(self.state).COOLING or self.request is None:
        return
    now = time.time()
    if self.cooling_started_at is not None:
        self.paused_total_s += max(0.0, now - self.cooling_started_at)
    self.cooling_started_at = None
    self._transition_state(type(self.state).ARMING, "cooling_resume_prepare")
    self._persist()
    resume_intent = ExecutionIntent(
        requested_voltage_v=self.request.voltage_v,
        requested_current_a=self.request.current_a,
        requested_mode="MANUAL_RESUME",
        source_decision_id=f"manual_resume:{self.identity_integration.identity.trace_id if self.identity_integration.identity else 'legacy'}",
        safety_context=SafetyContext(
            telemetry_state="FRESH",
            lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED",
            limits_reference="existing V2 guarded setter policy",
        ),
    )
    result = await self.execution_port.enable(
        resume_intent,
        identity=self.identity_integration.identity,
        recipe_voltage_ceiling_v=float(max_manual_voltage),
    )
    if not result.verified:
        self.stop_reason = result.reason or "cooling_resume_failed"
        self._transition_state(type(self.state).FAILED, self.stop_reason)
        self._persist()
        return
    self._transition_state(type(self.state).ACTIVE, "cooling_resume_confirmed")
    # Cooling breaks continuity-dependent delta confirmation; start a fresh
    # stop-condition segment after verified resume.
    self._reset_delta_tracking()
    self.finish_hold_started_at = None
    self._persist()
