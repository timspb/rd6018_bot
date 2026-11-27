"""Application orchestration for a Manual profile MAIN to MIX transition."""

from __future__ import annotations

import logging

from v3_core.canonical_events import EventType


logger = logging.getLogger("rd6018.manual")


async def advance_manual_profile_to_mix(session) -> None:
    self = session
    assert self.request is not None and self.request.profile is not None
    stage = self.request.profile.mix
    decision = self.phase_lifecycle.last_decision
    if decision is None or self.identity_integration.identity is None:
        logger.warning("MAIN -> MIX denied: V3 decision or lifecycle identity missing")
        return
    if not await self.execution_boundary.apply(
        decision,
        identity=self.identity_integration.identity,
    ):
        await self.stop("manual_main_to_mix_update_failed")
        return
    previous_stage = self.request.stage
    self.request = type(self.request)(
        voltage_v=stage.voltage_v,
        current_a=stage.current_a,
        battery_id=self.request.battery_id,
        capacity_ah=self.request.capacity_ah,
        notes=self.request.notes,
        profile=self.request.profile,
        stage="mix",
    )
    self.stop_reason = ""
    self.phase_transition_reason = "manual_main_to_mix"
    if self.identity_integration.identity is not None and self._manual_start_event_emitted:
        self.identity_integration.emit(
            event_type=EventType.PHASE_TRANSITION,
            phase_before=previous_stage or "main",
            phase_after="mix",
            reason=self.phase_transition_reason,
        )
    self._persist()
