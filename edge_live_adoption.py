from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from edge_safety_lease import EdgeLeaseState, EdgeSafetyLease, EdgeSafetyLeaseError


@dataclass(frozen=True)
class EdgeLiveAdoptionConfig:
    """Dedicated HANDS_OFF -> managed ownership-transfer command.

    This command is intentionally separate from ordinary ``arm()``. Normal arm keeps
    its verified-Output-OFF invariant; live adoption is allowed only when the edge node
    itself has a fresh direct register-18 readback proving Output is already ON.
    """

    entity: str = str(
        os.getenv("RD6018_EDGE_LIVE_ADOPT_ENTITY")
        or "button.rd6018_rd_6018_safety_lease_adopt_live_output"
    ).strip()


class EdgeLiveAdoption:
    """Positive-ACK live ownership acquisition for an already-ON RD6018.

    The existing :class:`EdgeSafetyLease` remains the single source of lease state and
    ACK geometry. This helper only adds the explicit ON-preserving acquisition command.

    A failed/ambiguous command deliberately leaves renewals suspended. Once a live-adopt
    command may have reached ESPHome, software must not blindly resume managed heartbeat
    authority while it is still logically HANDS_OFF. A fresh normal ``arm()`` later
    reopens renewal permission after a verified-OFF start.
    """

    def __init__(
        self,
        lease: EdgeSafetyLease,
        config: Optional[EdgeLiveAdoptionConfig] = None,
    ) -> None:
        self.lease = lease
        self.config = config or EdgeLiveAdoptionConfig()
        if not self.config.entity:
            raise ValueError("edge live-adoption entity must not be empty")

    async def _require_entity(self) -> None:
        state = await self.lease._state_value(self.config.entity)
        if state is None or str(state).strip().lower() in {
            "",
            "unknown",
            "unavailable",
        }:
            raise EdgeSafetyLeaseError(
                "edge live-adoption entity is missing/unavailable"
            )

    def _assert_adoptable(self, state: EdgeLeaseState) -> None:
        self.lease._assert_armable(state)
        if state.armed:
            raise EdgeSafetyLeaseError(
                "edge live adoption requires an unarmed HANDS_OFF lease"
            )
        if state.remaining_s is None:
            raise EdgeSafetyLeaseError("edge lease remaining time is unavailable")
        if state.remaining_s > self.lease.config.ack_remaining_slack_s:
            raise EdgeSafetyLeaseError(
                "edge live adoption requires an effectively-zero unarmed lease"
            )

    async def prepare(self) -> EdgeLeaseState:
        """Read-only preflight. No edge state or RD6018 register is changed."""
        self.lease.suspend_renewals()
        async with self.lease._operation_lock:
            await self._require_entity()
            state = await self.lease.read_state()
            self._assert_adoptable(state)
            return state

    async def adopt(
        self,
        *,
        expected_generation: Optional[int] = None,
    ) -> EdgeLeaseState:
        """Acquire the edge dead-man around an already-ON output.

        Positive ACK requires a generation change, armed healthy state, fresh direct
        Modbus evidence and a replenished lease. The ESPHome command itself additionally
        requires fresh register-18 Output-ON readback; Python never substitutes HA state
        for that edge-local check.
        """
        self.lease.suspend_renewals()
        async with self.lease._operation_lock:
            await self._require_entity()
            before = await self.lease.read_state()
            self._assert_adoptable(before)
            if (
                expected_generation is not None
                and before.generation != int(expected_generation)
            ):
                raise EdgeSafetyLeaseError(
                    "edge lease generation changed after live-adoption preflight"
                )
            if not await self.lease._press(self.config.entity):
                raise EdgeSafetyLeaseError("edge live-adoption command was rejected")

            latest = before
            attempts = max(1, int(self.lease.config.ack_attempts))
            for attempt in range(attempts):
                if attempt:
                    import asyncio

                    await asyncio.sleep(max(0.0, self.lease.config.ack_delay_s))
                latest = await self.lease.read_state()
                if (
                    latest.armed
                    and not latest.tripped
                    and not latest.boot_quarantine
                    and latest.generation != before.generation
                    and self.lease._fresh_modbus(latest)
                    and self.lease._full_lease_ack(latest)
                ):
                    self.lease._last_ack_monotonic = self.lease._monotonic()
                    self.lease.resume_renewals()
                    return latest

            raise EdgeSafetyLeaseError(
                "edge live adoption was not positively acknowledged by generation/readback"
            )
