from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from edge_safety_lease import EdgeLeaseState, EdgeSafetyLease, EdgeSafetyLeaseError


@dataclass(frozen=True)
class EdgeLiveAdoptionConfig:
    """Dedicated HANDS_OFF -> managed ownership-transfer command."""

    entity: str = ""
    protection_entity: str = ""
    ttl_entity: str = ""


class EdgeLiveAdoption:
    """Positive-ACK live ownership acquisition for an already-ON RD6018.

    Normal ``EdgeSafetyLease.arm()`` keeps its verified-Output-OFF invariant. This
    helper uses a distinct edge command whose ESPHome side requires fresh direct
    register-18 Output-ON readback and otherwise preserves Output/V/I/OVP/OCP.

    D061 additionally requires the canonical raw register-16 protection-code entity.
    Legacy OVP/OCP bit sensors are intentionally insufficient: register value 3 is OPP
    and must never be flattened into a misleading "no OVP/no OCP" managed preflight.

    Live adoption also proves the edge's configured watchdog TTL *before* pressing the
    ownership command. The deployed pre-D061 firmware used a 30-minute lease while D056
    accepts 15 minutes. A command-local TTL guard is still retained in ESPHome, but
    Python does not use a rejected button press as its compatibility probe.

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
        if renew.startswith("button.") and renew.endswith(suffix):
            base = renew[len("button.") : -len(suffix)]
            if not protection_entity:
                protection_entity = f"sensor.{base}_protection_status_code"
            if not ttl_entity:
                ttl_entity = f"sensor.{base}_safety_lease_ttl"
        if not protection_entity:
            raise ValueError(
                "raw protection-code entity is not configured and cannot be derived from renew entity"
            )
        if not ttl_entity:
            raise ValueError(
                "edge lease TTL entity is not configured and cannot be derived from renew entity"
            )
        self.config = EdgeLiveAdoptionConfig(
            entity=entity,
            protection_entity=protection_entity,
            ttl_entity=ttl_entity,
        )

    async def _require_entity(self) -> None:
        state = await self.lease._state_value(self.config.entity)
        # Home Assistant button entities normally expose state ``unknown``; unlike a
        # sensor, that is not evidence that the entity is missing. ``None`` means no
        # entity was returned and ``unavailable`` means the node/entity cannot serve it.
        if state is None or str(state).strip().lower() == "unavailable":
            raise EdgeSafetyLeaseError(
                "edge live-adoption entity is missing/unavailable"
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

    @staticmethod
    def _timestamp(value: Any) -> Optional[float]:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text).timestamp()
        except (ValueError, OverflowError):
            return None
        return parsed if math.isfinite(parsed) else None

    async def _require_raw_protection_normal(self) -> None:
        """Require fresh authoritative register-16 code == NORMAL (0).

        This is deliberately independent from the legacy OVP/OCP booleans. The target
        V2 ESPHome telemetry package publishes register 16 as one raw status code:
        0 normal, 1 OVP, 2 OCP, 3 OPP. Missing/stale/unknown raw telemetry blocks D061.
        """
        get_state = getattr(self.lease.hass, "get_state", None)
        if not callable(get_state):
            raise EdgeSafetyLeaseError(
                "Home Assistant adapter cannot read raw RD6018 protection status"
            )
        state, attrs = await get_state(self.config.protection_entity)
        normalized = str(state).strip().lower() if state is not None else ""
        if state is None or normalized in {"", "unknown", "unavailable"}:
            raise EdgeSafetyLeaseError(
                "raw RD6018 protection-code entity is missing/unavailable"
            )
        try:
            parsed = float(state)
        except (TypeError, ValueError) as exc:
            raise EdgeSafetyLeaseError(
                "raw RD6018 protection code is invalid"
            ) from exc
        code = int(round(parsed))
        if not math.isfinite(parsed) or abs(parsed - code) > 1e-9:
            raise EdgeSafetyLeaseError("raw RD6018 protection code is invalid")
        if code != 0:
            labels = {1: "OVP", 2: "OCP", 3: "OPP"}
            label = labels.get(code, f"UNKNOWN({code})")
            raise EdgeSafetyLeaseError(
                f"raw RD6018 protection status is not normal: {label}"
            )

        metadata = attrs if isinstance(attrs, dict) else {}
        timestamp = self._timestamp(metadata.get("_ha_last_reported"))
        if timestamp is None:
            timestamp = self._timestamp(metadata.get("_ha_last_updated"))
        if timestamp is None:
            raise EdgeSafetyLeaseError(
                "raw RD6018 protection freshness timestamp is unavailable"
            )
        age = max(0.0, time.time() - timestamp)
        if age > float(self.lease.config.max_modbus_age_s):
            raise EdgeSafetyLeaseError(
                f"raw RD6018 protection status is stale ({age:.1f}s)"
            )

    def _install_renewal_protection_gate(self) -> None:
        """Keep authoritative raw protection evidence mandatory after D061 adoption.

        StrictRuntimeSafetyGuard calls ``renew_if_due()`` on every managed live poll,
        not only when the five-minute heartbeat is due. Wrapping that boundary makes
        loss/OPP/unknown raw register-16 telemetry fail the managed lease immediately
        even though the generic runtime still supports legacy OVP/OCP sensors for
        non-adopted migration paths. Restart does not need to preserve this wrapper:
        D061 authority itself is never resumed after restart.
        """
        if bool(getattr(self.lease, "_d061_raw_protection_gate_installed", False)):
            return
        original = self.lease.renew_if_due

        async def guarded_renew_if_due() -> EdgeLeaseState:
            await self._require_raw_protection_normal()
            return await original()

        self.lease.renew_if_due = guarded_renew_if_due
        self.lease._d061_raw_protection_gate_installed = True

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
            await self._require_target_ttl()
            await self._require_raw_protection_normal()
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
        Modbus evidence, a replenished 15-minute lease and fresh raw register-16 NORMAL
        both immediately before the edge command and after its acknowledgement. The
        ESPHome command itself also requires fresh direct register-18 Output-ON and
        direct register-16 NORMAL readback; Python never substitutes HA state for those
        edge-local checks.
        """
        import asyncio

        self.lease.suspend_renewals()
        async with self.lease._operation_lock:
            await self._require_entity()
            await self._require_target_ttl()
            await self._require_raw_protection_normal()
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
                    # Do not reopen heartbeat authority until raw protection telemetry
                    # has independently survived the ownership command/ACK boundary.
                    await self._require_target_ttl()
                    await self._require_raw_protection_normal()
                    self._install_renewal_protection_gate()
                    self.lease._last_ack_monotonic = self.lease._monotonic()
                    self.lease.resume_renewals()
                    return latest

            raise EdgeSafetyLeaseError(
                "edge live adoption was not positively acknowledged by generation/readback"
            )
