from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Optional


def _env(name: str, default: str) -> str:
    value = str(os.getenv(name) or "").strip()
    return value or default


# Home Assistant generated these IDs for the deployed RD6018 ESPHome node.
# Keep the prefix configurable so a renamed/recreated device does not require a code
# patch; individual entity IDs remain overrideable for unusual HA registries.
EDGE_ENTITY_PREFIX = _env("RD6018_EDGE_ENTITY_PREFIX", "rd6018_rd_6018")


@dataclass(frozen=True)
class EdgeSafetyLeaseConfig:
    """Contract with the local ESPHome safety lease running beside RD6018."""

    renew_entity: str = _env(
        "RD6018_EDGE_RENEW_ENTITY",
        f"button.{EDGE_ENTITY_PREFIX}_safety_lease_renew",
    )
    disarm_entity: str = _env(
        "RD6018_EDGE_DISARM_ENTITY",
        f"button.{EDGE_ENTITY_PREFIX}_safety_lease_disarm",
    )
    hands_off_release_entity: str = _env(
        "RD6018_EDGE_HANDS_OFF_RELEASE_ENTITY",
        f"button.{EDGE_ENTITY_PREFIX}_safety_lease_release_to_hands_off",
    )
    armed_entity: str = _env(
        "RD6018_EDGE_ARMED_ENTITY",
        f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_lease_armed",
    )
    tripped_entity: str = _env(
        "RD6018_EDGE_TRIPPED_ENTITY",
        f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_lease_tripped",
    )
    boot_quarantine_entity: str = _env(
        "RD6018_EDGE_BOOT_QUARANTINE_ENTITY",
        f"binary_sensor.{EDGE_ENTITY_PREFIX}_safety_boot_quarantine",
    )
    generation_entity: str = _env(
        "RD6018_EDGE_GENERATION_ENTITY",
        f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_generation",
    )
    modbus_age_entity: str = _env(
        "RD6018_EDGE_MODBUS_AGE_ENTITY",
        f"sensor.{EDGE_ENTITY_PREFIX}_safety_modbus_age",
    )
    remaining_entity: str = _env(
        "RD6018_EDGE_REMAINING_ENTITY",
        f"sensor.{EDGE_ENTITY_PREFIX}_safety_lease_remaining",
    )

    # Accepted V2 control-loss budget: three renewal opportunities inside one lease.
    lease_ttl_s: float = 15.0 * 60.0
    renew_interval_s: float = 5.0 * 60.0
    max_modbus_age_s: float = 20.0
    ack_remaining_slack_s: float = 15.0
    ack_attempts: int = 12
    ack_delay_s: float = 0.25
    # Normal renew/adopt ACKs are generation-based and usually arrive quickly. A
    # verified-OFF disarm is different: production HA may publish the edge binary
    # state a few seconds after register-18 has already confirmed physical OFF. Give
    # only that readback a bounded 10 s convergence window; the 900 s edge TTL and
    # renewal cadence are unchanged.
    disarm_ack_attempts: int = 41
    disarm_ack_delay_s: float = 0.25


@dataclass(frozen=True)
class EdgeLeaseState:
    armed: bool
    tripped: bool
    boot_quarantine: bool
    generation: int
    modbus_age_s: float
    remaining_s: Optional[float]


class EdgeSafetyLeaseError(RuntimeError):
    pass


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _bool_state(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


class EdgeSafetyLease:
    """Positive-acknowledged lease for the local RD6018 ESPHome watchdog.

    A HTTP 200 from Home Assistant is not considered a renewal. A renewal is valid
    only when the edge node publishes a different generation, says the lease is
    armed, reports a recent direct Modbus observation from RD6018, exposes a newly
    replenished near-full timeout, and is neither tripped nor in boot quarantine.

    Lease operations are serialized. HANDS_OFF transfer can synchronously suspend
    future renewals before waiting for an in-flight heartbeat to finish, preventing a
    late renewal from re-arming the watchdog after ownership has been released.
    """

    def __init__(
        self,
        hass: Any,
        config: Optional[EdgeSafetyLeaseConfig] = None,
        *,
        monotonic=time.monotonic,
    ) -> None:
        self.hass = hass
        self.config = config or EdgeSafetyLeaseConfig()
        self._monotonic = monotonic
        self._last_ack_monotonic: Optional[float] = None
        self._operation_lock = asyncio.Lock()
        self._renewals_suspended = False

        if self.config.lease_ttl_s <= 0:
            raise ValueError("edge lease TTL must be positive")
        if not (0 < self.config.renew_interval_s < self.config.lease_ttl_s):
            raise ValueError("edge lease renewal interval must be between zero and TTL")
        if not (0 <= self.config.ack_remaining_slack_s < self.config.lease_ttl_s):
            raise ValueError("edge lease acknowledgement slack is invalid")
        if int(self.config.ack_attempts) < 1 or int(self.config.disarm_ack_attempts) < 1:
            raise ValueError("edge lease acknowledgement attempts must be positive")
        if self.config.ack_delay_s < 0 or self.config.disarm_ack_delay_s < 0:
            raise ValueError("edge lease acknowledgement delay cannot be negative")

    @property
    def last_ack_age_s(self) -> Optional[float]:
        if self._last_ack_monotonic is None:
            return None
        return max(0.0, self._monotonic() - self._last_ack_monotonic)

    @property
    def renewals_suspended(self) -> bool:
        return bool(self._renewals_suspended)

    def suspend_renewals(self) -> None:
        """Prevent new/pending heartbeat calls from renewing the edge lease."""
        self._renewals_suspended = True

    def resume_renewals(self) -> None:
        """Undo a pre-command HANDS_OFF preparation that did not transfer ownership."""
        self._renewals_suspended = False

    def renewal_due(self) -> bool:
        age = self.last_ack_age_s
        return age is None or age >= self.config.renew_interval_s

    async def _state_value(self, entity_id: str) -> Any:
        get_state = getattr(self.hass, "get_state", None)
        if get_state is None:
            raise EdgeSafetyLeaseError("Home Assistant adapter cannot read lease entities")
        state, _attrs = await get_state(entity_id)
        return state

    async def read_state(self) -> EdgeLeaseState:
        (
            armed_raw,
            tripped_raw,
            boot_quarantine_raw,
            generation_raw,
            modbus_age_raw,
            remaining_raw,
        ) = await asyncio.gather(
            self._state_value(self.config.armed_entity),
            self._state_value(self.config.tripped_entity),
            self._state_value(self.config.boot_quarantine_entity),
            self._state_value(self.config.generation_entity),
            self._state_value(self.config.modbus_age_entity),
            self._state_value(self.config.remaining_entity),
        )
        armed = _bool_state(armed_raw)
        tripped = _bool_state(tripped_raw)
        boot_quarantine = _bool_state(boot_quarantine_raw)
        generation_f = _finite_float(generation_raw)
        modbus_age = _finite_float(modbus_age_raw)
        remaining = _finite_float(remaining_raw)
        if (
            armed is None
            or tripped is None
            or boot_quarantine is None
            or generation_f is None
            or modbus_age is None
            or remaining is None
        ):
            missing = []
            if armed is None:
                missing.append(self.config.armed_entity)
            if tripped is None:
                missing.append(self.config.tripped_entity)
            if boot_quarantine is None:
                missing.append(self.config.boot_quarantine_entity)
            if generation_f is None:
                missing.append(self.config.generation_entity)
            if modbus_age is None:
                missing.append(self.config.modbus_age_entity)
            if remaining is None:
                missing.append(self.config.remaining_entity)
            raise EdgeSafetyLeaseError(
                "edge lease telemetry is missing/unavailable: " + ", ".join(missing)
            )
        generation = int(generation_f)
        if generation < 0 or abs(generation_f - generation) > 1e-6:
            raise EdgeSafetyLeaseError("edge lease generation is invalid")
        if modbus_age < 0:
            raise EdgeSafetyLeaseError("edge Modbus age is invalid")
        if remaining < 0 or remaining > self.config.lease_ttl_s + self.config.ack_remaining_slack_s:
            raise EdgeSafetyLeaseError("edge lease remaining time is invalid")
        return EdgeLeaseState(
            armed=armed,
            tripped=tripped,
            boot_quarantine=boot_quarantine,
            generation=generation,
            modbus_age_s=modbus_age,
            remaining_s=remaining,
        )

    async def _press(self, entity_id: str) -> bool:
        press = getattr(self.hass, "press_button", None)
        try:
            if press is not None:
                return bool(await press(entity_id))

            ensure_session = getattr(self.hass, "_ensure_session", None)
            base_url = str(getattr(self.hass, "base_url", "") or "").rstrip("/")
            if ensure_session is None or not base_url:
                raise EdgeSafetyLeaseError(
                    "Home Assistant adapter cannot press safety lease buttons"
                )
            session = await ensure_session()
            async with session.post(
                f"{base_url}/api/services/button/press",
                json={"entity_id": entity_id},
            ) as response:
                return response.status in (200, 201)
        except EdgeSafetyLeaseError:
            raise
        except Exception as exc:
            raise EdgeSafetyLeaseError(
                f"edge lease service call failed: {type(exc).__name__}"
            ) from exc

    def _fresh_modbus(self, state: EdgeLeaseState) -> bool:
        return state.modbus_age_s <= self.config.max_modbus_age_s

    def _full_lease_ack(self, state: EdgeLeaseState) -> bool:
        assert state.remaining_s is not None
        return state.remaining_s >= (
            self.config.lease_ttl_s - self.config.ack_remaining_slack_s
        )

    def _assert_armable(self, state: EdgeLeaseState) -> None:
        if state.boot_quarantine:
            raise EdgeSafetyLeaseError("edge safety boot quarantine is active")
        if state.tripped:
            raise EdgeSafetyLeaseError("edge safety lease trip is latched")
        if not self._fresh_modbus(state):
            raise EdgeSafetyLeaseError(
                f"RD6018 Modbus is stale at edge ({state.modbus_age_s:.1f}s)"
            )

    async def _renew_locked(self, *, force: bool) -> EdgeLeaseState:
        if self._renewals_suspended:
            raise EdgeSafetyLeaseError("edge lease renewal is suspended for ownership transfer")

        if not force and not self.renewal_due():
            state = await self.read_state()
            if state.boot_quarantine:
                raise EdgeSafetyLeaseError("edge safety boot quarantine is active")
            if state.tripped:
                raise EdgeSafetyLeaseError("edge safety lease trip is latched")
            if not state.armed or not self._fresh_modbus(state):
                raise EdgeSafetyLeaseError("edge lease is not healthy between renewals")
            assert state.remaining_s is not None
            required_remaining = self.config.renew_interval_s + self.config.ack_remaining_slack_s
            if state.remaining_s <= required_remaining:
                raise EdgeSafetyLeaseError("edge lease remaining time is unexpectedly short")
            return state

        before = await self.read_state()
        self._assert_armable(before)
        if not await self._press(self.config.renew_entity):
            raise EdgeSafetyLeaseError("edge lease renew command was rejected")

        latest = before
        attempts = max(1, int(self.config.ack_attempts))
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(max(0.0, self.config.ack_delay_s))
            latest = await self.read_state()
            if (
                latest.armed
                and not latest.tripped
                and not latest.boot_quarantine
                and latest.generation != before.generation
                and self._fresh_modbus(latest)
                and self._full_lease_ack(latest)
            ):
                self._last_ack_monotonic = self._monotonic()
                return latest

        raise EdgeSafetyLeaseError(
            "edge lease renewal was not positively acknowledged by generation/readback"
        )

    async def renew(self, *, force: bool = False) -> EdgeLeaseState:
        async with self._operation_lock:
            return await self._renew_locked(force=force)

    async def arm(self) -> EdgeLeaseState:
        async with self._operation_lock:
            # A fresh managed enable explicitly re-opens renewal authority. The edge
            # still enforces its own initial-arm Output-OFF requirement.
            self._renewals_suspended = False
            return await self._renew_locked(force=True)

    async def renew_if_due(self) -> EdgeLeaseState:
        return await self.renew(force=False)

    async def disarm(self) -> bool:
        # Normal disarm is still the verified-OFF path. Suspending before the lock also
        # stops a heartbeat that was queued behind this operation from re-arming later.
        self._renewals_suspended = True
        async with self._operation_lock:
            if not await self._press(self.config.disarm_entity):
                return False
            attempts = max(1, int(self.config.disarm_ack_attempts))
            for attempt in range(attempts):
                if attempt:
                    await asyncio.sleep(max(0.0, self.config.disarm_ack_delay_s))
                try:
                    state = await self.read_state()
                except EdgeSafetyLeaseError:
                    continue
                if (
                    not state.armed
                    and not state.boot_quarantine
                    and state.remaining_s is not None
                    and state.remaining_s <= self.config.ack_remaining_slack_s
                ):
                    self._last_ack_monotonic = None
                    return True
            return False

    async def prepare_hands_off_release(self) -> EdgeLeaseState:
        """Verify that a live managed lease can be explicitly released while ON.

        Caller must first suspend renewals. No edge state is changed here.
        """
        async with self._operation_lock:
            if not self._renewals_suspended:
                raise EdgeSafetyLeaseError(
                    "HANDS_OFF release preparation requires suspended renewals"
                )
            button_state = await self._state_value(self.config.hands_off_release_entity)
            if button_state is None or str(button_state).strip().lower() == "unavailable":
                raise EdgeSafetyLeaseError(
                    "edge HANDS_OFF release entity is missing/unavailable"
                )
            state = await self.read_state()
            self._assert_armable(state)
            if not state.armed:
                raise EdgeSafetyLeaseError(
                    "managed edge lease is not armed before HANDS_OFF release"
                )
            return state

    async def release_to_hands_off(
        self,
        *,
        expected_generation: Optional[int] = None,
    ) -> EdgeLeaseState:
        """Release the local dead-man while keeping an already-ON RD output untouched.

        This is deliberately distinct from ``disarm()``. ESPHome normal disarm keeps
        its verified-Output-OFF invariant; only the explicit HANDS_OFF release command
        may clear the managed-session bit while Output is ON.
        """
        self._renewals_suspended = True
        async with self._operation_lock:
            before = await self.read_state()
            self._assert_armable(before)
            if not before.armed:
                raise EdgeSafetyLeaseError(
                    "managed edge lease is not armed before HANDS_OFF release"
                )
            if expected_generation is not None and before.generation != int(expected_generation):
                raise EdgeSafetyLeaseError(
                    "edge lease generation changed after HANDS_OFF release preflight"
                )
            if not await self._press(self.config.hands_off_release_entity):
                raise EdgeSafetyLeaseError("edge HANDS_OFF release command was rejected")

            latest = before
            attempts = max(1, int(self.config.ack_attempts))
            for attempt in range(attempts):
                if attempt:
                    await asyncio.sleep(max(0.0, self.config.ack_delay_s))
                latest = await self.read_state()
                if (
                    not latest.armed
                    and not latest.tripped
                    and not latest.boot_quarantine
                    and latest.generation != before.generation
                    and self._fresh_modbus(latest)
                    and latest.remaining_s is not None
                    and latest.remaining_s <= self.config.ack_remaining_slack_s
                ):
                    self._last_ack_monotonic = None
                    return latest

            raise EdgeSafetyLeaseError(
                "edge HANDS_OFF release was not positively acknowledged by generation/readback"
            )
