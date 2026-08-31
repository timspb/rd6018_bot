from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from edge_safety_lease import EdgeLeaseState, EdgeSafetyLease, EdgeSafetyLeaseError


@dataclass(frozen=True)
class EdgeLiveAdoptionConfig:
    """Dedicated HANDS_OFF -> managed ownership-transfer command."""

    entity: str = ""


class EdgeLiveAdoption:
    """Positive-ACK live ownership acquisition for an already-ON RD6018.

    Normal ``EdgeSafetyLease.arm()`` keeps its verified-Output-OFF invariant. This
    helper uses a distinct edge command whose ESPHome side requires fresh direct
    register-18 Output-ON readback and otherwise preserves Output/V/I/OVP/OCP.

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
        configured = config or EdgeLiveAdoptionConfig()
        entity = str(configured.entity or os.getenv("RD6018_EDGE_LIVE_ADOPT_ENTITY") or "").strip()
        if not entity:
            renew = str(getattr(self.lease.config, "renew_entity", "") or "").strip()
            suffix = "_safety_lease_renew"
            if renew.endswith(suffix):
                entity = renew[: -len(suffix)] + "_safety_lease_adopt_live_output"
            else:
                raise ValueError(
                    "edge live-adoption entity is not configured and cannot be derived from renew entity"
                )
        self.config = EdgeLiveAdoptionConfig(entity=entity)

    async def _require_entity(self) -> None:
        state = await self.lease._state_value(self.config.entity)
        # Home Assistant button entities normally expose state ``unknown``; unlike a
        # sensor, that is not evidence that the entity is missing. ``None`` means no
        # entity was returned and ``unavailable`` means the node/entity cannot serve it.
        if state is None or str(state).strip().lower() == "unavailable":
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
        import asyncio

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
