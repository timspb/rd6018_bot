from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Optional

from runtime.safety.edge_lease import (
    EdgeLeaseState,
    EdgeSafetyLease,
    EdgeSafetyLeaseError,
    _bool_state,
)
from runtime.safety.protection_boundary import ProtectionVerdict


@dataclass(frozen=True)
class EdgeLiveAdoptionConfig:
    """Dedicated HANDS_OFF -> managed ownership-transfer command."""

    entity: str = ""
    protection_entity: str = ""
    ttl_entity: str = ""
    autonomous_entity: str = ""


class EdgeLiveAdoption:
    """Positive-ACK live ownership acquisition for an already-ON RD6018.

    Normal ``EdgeSafetyLease.arm()`` keeps its verified-Output-OFF invariant. This
    helper uses a distinct edge command whose ESPHome side requires fresh direct
    register-18 Output-ON readback and otherwise preserves Output/V/I.

    D061 additionally requires a fresh Safety-owned hardware-protection verdict.

    Live adoption also proves the edge's configured watchdog TTL *before* pressing the
    ownership command. The deployed pre-D061 firmware used a 30-minute lease while D056
    accepts 15 minutes. A command-local TTL guard is still retained in ESPHome, but
    Python does not use a rejected button press as its compatibility probe.

    Explicit D065 AUTONOMOUS is not a D061 source state. It is rejected read-only before
    the edge-command uncertainty boundary so a stale Pb-adoption callback cannot turn an
    autonomous generic PSU into verified-OFF containment merely because the ESP command
    correctly refused the takeover.

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
        self._command_may_have_executed = False
        configured = config or EdgeLiveAdoptionConfig()
        entity = str(
            configured.entity
            or os.getenv("RD6018_EDGE_LIVE_ADOPT_ENTITY")
            or ""
        ).strip()
        renew = str(getattr(self.lease.config, "renew_entity", "") or "").strip()
        suffix = "_safety_lease_renew"
        if not entity:
            if renew.endswith(suffix):
                entity = renew[: -len(suffix)] + "_safety_lease_adopt_live_output"
            else:
                raise ValueError(
                    "edge live-adoption entity is not configured and cannot be derived from renew entity"
                )

        protection_entity = str(
            configured.protection_entity
            or os.getenv("RD6018_EDGE_PROTECTION_CODE_ENTITY")
            or ""
        ).strip()
        ttl_entity = str(
            configured.ttl_entity
            or os.getenv("RD6018_EDGE_TTL_ENTITY")
            or ""
        ).strip()
        autonomous_entity = str(
            configured.autonomous_entity
            or os.getenv("RD6018_EDGE_AUTONOMOUS_ENTITY")
            or ""
        ).strip()
        if renew.startswith("button.") and renew.endswith(suffix):
            base = renew[len("button.") : -len(suffix)]
            if not protection_entity:
                protection_entity = f"sensor.{base}_protection_status_code"
            if not ttl_entity:
                ttl_entity = f"sensor.{base}_safety_lease_ttl"
            if not autonomous_entity:
                autonomous_entity = f"binary_sensor.{base}_safety_autonomous_mode"
        if not protection_entity:
            raise ValueError(
                "hardware protection entity is not configured and cannot be derived from renew entity"
            )
        if not ttl_entity:
            raise ValueError(
                "edge lease TTL entity is not configured and cannot be derived from renew entity"
            )
        if not autonomous_entity:
            raise ValueError(
                "edge autonomous entity is not configured and cannot be derived from renew entity"
            )
        self.config = EdgeLiveAdoptionConfig(
            entity=entity,
            protection_entity=protection_entity,
            ttl_entity=ttl_entity,
            autonomous_entity=autonomous_entity,
        )

    @property
    def command_may_have_executed(self) -> bool:
        """Whether this transaction crossed the edge-command uncertainty boundary."""
        return bool(self._command_may_have_executed)

    async def _require_entity(self) -> None:
        await self.lease.require_button_available(self.config.entity)

    async def _require_not_autonomous(self) -> None:
        raw = await self.lease._state_value(self.config.autonomous_entity)
        autonomous = _bool_state(raw)
        if autonomous is None:
            raise EdgeSafetyLeaseError(
                "edge autonomous authority is missing/unavailable; live adoption is blocked"
            )
        if autonomous:
            raise EdgeSafetyLeaseError(
                "edge AUTONOMOUS is active; exit AUTONOMOUS with confirmed Output OFF before live Pb adoption"
            )

    async def _require_target_ttl(self) -> None:
        state = await self.lease._state_value(self.config.ttl_entity)
        try:
            ttl_s = float(state)
        except (TypeError, ValueError) as exc:
            raise EdgeSafetyLeaseError(
                "edge lease TTL contract entity is missing/unavailable"
            ) from exc
        if not math.isfinite(ttl_s):
            raise EdgeSafetyLeaseError("edge lease TTL contract is invalid")
        expected = float(self.lease.config.lease_ttl_s)
        if abs(ttl_s - expected) > 1.0:
            raise EdgeSafetyLeaseError(
                f"edge live adoption requires {expected:.0f}s lease TTL, got {ttl_s:.0f}s"
            )

    async def _require_protection_clear(self) -> None:
        """Require the Safety-owned hardware-protection verdict to be CLEAR."""
        try:
            assessment = await self.lease.read_protection_assessment(
                self.config.protection_entity
            )
        except EdgeSafetyLeaseError as exc:
            raise EdgeSafetyLeaseError(
                "hardware protection evidence is unavailable"
            ) from exc
        if assessment.verdict is ProtectionVerdict.TRIPPED:
            raise EdgeSafetyLeaseError("hardware protection is tripped")
        if assessment.verdict is ProtectionVerdict.UNKNOWN:
            raise EdgeSafetyLeaseError(
                "hardware protection state is unavailable/unknown"
            )

    def _install_renewal_protection_gate(self) -> None:
        """Keep the independent Safety protection gate on every managed poll."""
        if bool(getattr(self.lease, "_d061_protection_gate_installed", False)):
            return
        original = self.lease.renew_if_due

        async def guarded_renew_if_due() -> EdgeLeaseState:
            await self._require_protection_clear()
            return await original()

        self.lease.renew_if_due = guarded_renew_if_due
        self.lease._d061_protection_gate_installed = True

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
        self._command_may_have_executed = False
        self.lease.suspend_renewals()
        async with self.lease._operation_lock:
            await self._require_entity()
            await self._require_not_autonomous()
            await self._require_target_ttl()
            await self._require_protection_clear()
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
        Modbus evidence, a replenished 15-minute lease and a CLEAR Safety protection
        verdict both immediately before the edge command and after its acknowledgement.
        The ESPHome command keeps its own local hardware interlocks; this coordinator
        does not decode protection registers or bypass the Safety boundary.
        """
        import asyncio

        self._command_may_have_executed = False
        self.lease.suspend_renewals()
        async with self.lease._operation_lock:
            await self._require_entity()
            await self._require_not_autonomous()
            await self._require_target_ttl()
            await self._require_protection_clear()
            before = await self.lease.read_state()
            self._assert_adoptable(before)
            if (
                expected_generation is not None
                and before.generation != int(expected_generation)
            ):
                raise EdgeSafetyLeaseError(
                    "edge lease generation changed after live-adoption preflight"
                )
            # Re-check the independent edge operation mode immediately before the
            # command uncertainty boundary. ESPHome also refuses the command if a
            # concurrent operator transition races this read.
            await self._require_not_autonomous()

            # From this point onward an exception/negative HTTP result cannot prove
            # that the command did not reach ESPHome. Coordinator containment must
            # therefore treat the edge ownership state as ambiguous and drive OFF.
            self._command_may_have_executed = True
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
                    # Do not reopen heartbeat authority until the independent Safety
                    # protection verdict survives the ownership command/ACK boundary.
                    await self._require_target_ttl()
                    await self._require_protection_clear()
                    self._install_renewal_protection_gate()
                    self.lease._last_ack_monotonic = self.lease._monotonic()
                    self.lease.resume_renewals()
                    return latest

            raise EdgeSafetyLeaseError(
                "edge live adoption was not positively acknowledged by generation/readback"
            )
