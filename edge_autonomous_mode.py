from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from edge_safety_lease import EdgeLeaseState, EdgeSafetyLease, EdgeSafetyLeaseError, _bool_state


@dataclass(frozen=True)
class EdgeAutonomousConfig:
    """Explicit edge operation-mode entities; HANDS_OFF is not part of this contract."""

    autonomous_entity: str = ""
    enter_entity: str = ""
    exit_entity: str = ""


class EdgeAutonomousAuthority:
    """Positive-ACK controller for the persistent ESPHome AUTONOMOUS bit.

    Enter/exit are deliberately Output-OFF-only at the edge.  Python never treats an
    unarmed lease, HANDS_OFF, network loss, or a missing session as autonomous proof.
    The ESPHome buttons independently require fresh direct register-18 OFF evidence;
    this wrapper additionally requires generation change and fresh healthy edge state.
    """

    def __init__(
        self,
        lease: EdgeSafetyLease,
        config: Optional[EdgeAutonomousConfig] = None,
    ) -> None:
        self.lease = lease
        configured = config or EdgeAutonomousConfig()
        renew = str(getattr(lease.config, "renew_entity", "") or "").strip()
        suffix = "_safety_lease_renew"
        base = ""
        if renew.startswith("button.") and renew.endswith(suffix):
            base = renew[len("button.") : -len(suffix)]

        self.config = EdgeAutonomousConfig(
            autonomous_entity=str(
                configured.autonomous_entity
                or os.getenv("RD6018_EDGE_AUTONOMOUS_ENTITY")
                or (f"binary_sensor.{base}_safety_autonomous_mode" if base else "")
            ).strip(),
            enter_entity=str(
                configured.enter_entity
                or os.getenv("RD6018_EDGE_ENTER_AUTONOMOUS_ENTITY")
                or (f"button.{base}_safety_enter_autonomous" if base else "")
            ).strip(),
            exit_entity=str(
                configured.exit_entity
                or os.getenv("RD6018_EDGE_EXIT_AUTONOMOUS_ENTITY")
                or (f"button.{base}_safety_exit_autonomous" if base else "")
            ).strip(),
        )
        if not all(
            (
                self.config.autonomous_entity,
                self.config.enter_entity,
                self.config.exit_entity,
            )
        ):
            raise ValueError(
                "edge autonomous entities are not configured and cannot be derived from renew entity"
            )
        self._command_may_have_executed = False

    @property
    def command_may_have_executed(self) -> bool:
        return bool(self._command_may_have_executed)

    async def read_autonomous(self) -> bool:
        raw = await self.lease._state_value(self.config.autonomous_entity)
        parsed = _bool_state(raw)
        if parsed is None:
            raise EdgeSafetyLeaseError(
                "edge autonomous authority is missing/unavailable"
            )
        return parsed

    async def _require_button(self, entity_id: str) -> None:
        state = await self.lease._state_value(entity_id)
        if state is None or str(state).strip().lower() == "unavailable":
            raise EdgeSafetyLeaseError(
                f"edge autonomous command entity is missing/unavailable: {entity_id}"
            )

    def _assert_unmanaged_healthy(self, state: EdgeLeaseState) -> None:
        if state.armed:
            raise EdgeSafetyLeaseError(
                "autonomous transition requires the managed edge lease to be unarmed"
            )
        if state.tripped:
            raise EdgeSafetyLeaseError("edge safety lease trip is latched")
        if state.boot_quarantine:
            raise EdgeSafetyLeaseError("edge safety boot quarantine is active")
        if not self.lease._fresh_modbus(state):
            raise EdgeSafetyLeaseError(
                f"RD6018 Modbus is stale at edge ({state.modbus_age_s:.1f}s)"
            )
        if state.remaining_s is None:
            raise EdgeSafetyLeaseError("edge lease remaining time is unavailable")
        if state.remaining_s > self.lease.config.ack_remaining_slack_s:
            raise EdgeSafetyLeaseError(
                "autonomous transition requires an effectively-zero managed lease"
            )

    async def _transition(self, *, target: bool) -> EdgeLeaseState:
        self._command_may_have_executed = False
        self.lease.suspend_renewals()
        entity = self.config.enter_entity if target else self.config.exit_entity
        async with self.lease._operation_lock:
            await self._require_button(entity)
            before_mode = await self.read_autonomous()
            if before_mode is target:
                state = await self.lease.read_state()
                self._assert_unmanaged_healthy(state)
                return state

            before = await self.lease.read_state()
            self._assert_unmanaged_healthy(before)

            self._command_may_have_executed = True
            if not await self.lease._press(entity):
                raise EdgeSafetyLeaseError(
                    "edge autonomous transition command was rejected"
                )

            latest = before
            attempts = max(1, int(self.lease.config.ack_attempts))
            for attempt in range(attempts):
                if attempt:
                    await asyncio.sleep(max(0.0, self.lease.config.ack_delay_s))
                try:
                    mode = await self.read_autonomous()
                    latest = await self.lease.read_state()
                    self._assert_unmanaged_healthy(latest)
                except EdgeSafetyLeaseError:
                    continue
                if mode is target and latest.generation != before.generation:
                    self.lease._last_ack_monotonic = None
                    return latest

            raise EdgeSafetyLeaseError(
                "edge autonomous transition was not positively acknowledged by mode/generation/readback"
            )

    async def enter(self) -> EdgeLeaseState:
        return await self._transition(target=True)

    async def exit(self) -> EdgeLeaseState:
        return await self._transition(target=False)
