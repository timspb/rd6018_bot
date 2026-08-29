from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class EdgeSafetyLeaseConfig:
    """Contract with the local ESPHome safety lease running beside RD6018.

    The lease is deliberately shorter than any Pb recovery stage. The bot must
    periodically prove that it can still reach the edge node *and* that the edge
    node is still receiving fresh Modbus data from RD6018. If renewals stop, the
    ESPHome node turns the RD output off locally without depending on HA or the bot.
    """

    renew_entity: str = "button.rd_6018_safety_lease_renew"
    disarm_entity: str = "button.rd_6018_safety_lease_disarm"
    armed_entity: str = "binary_sensor.rd_6018_safety_lease_armed"
    generation_entity: str = "sensor.rd_6018_safety_lease_generation"
    modbus_age_entity: str = "sensor.rd_6018_safety_modbus_age"
    remaining_entity: str = "sensor.rd_6018_safety_lease_remaining"

    lease_ttl_s: float = 30.0 * 60.0
    # 10/30 gives room for two missed renewal opportunities. The originally
    # proposed 15/30 cadence is safe too, but leaves less scheduling/network margin.
    renew_interval_s: float = 10.0 * 60.0
    max_modbus_age_s: float = 20.0
    ack_attempts: int = 12
    ack_delay_s: float = 0.25


@dataclass(frozen=True)
class EdgeLeaseState:
    armed: bool
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
    only when the edge node publishes a *different* generation, says the lease is
    armed, and reports a recent direct Modbus observation from RD6018. This prevents
    stale HA state from masquerading as a healthy control path.
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

    @property
    def last_ack_age_s(self) -> Optional[float]:
        if self._last_ack_monotonic is None:
            return None
        return max(0.0, self._monotonic() - self._last_ack_monotonic)

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
        armed_raw, generation_raw, modbus_age_raw, remaining_raw = await asyncio.gather(
            self._state_value(self.config.armed_entity),
            self._state_value(self.config.generation_entity),
            self._state_value(self.config.modbus_age_entity),
            self._state_value(self.config.remaining_entity),
        )
        armed = _bool_state(armed_raw)
        generation_f = _finite_float(generation_raw)
        modbus_age = _finite_float(modbus_age_raw)
        remaining = _finite_float(remaining_raw)
        if armed is None or generation_f is None or modbus_age is None:
            raise EdgeSafetyLeaseError("edge lease telemetry is missing/unavailable")
        generation = int(generation_f)
        if generation < 0:
            raise EdgeSafetyLeaseError("edge lease generation is invalid")
        if modbus_age < 0:
            raise EdgeSafetyLeaseError("edge Modbus age is invalid")
        return EdgeLeaseState(
            armed=armed,
            generation=generation,
            modbus_age_s=modbus_age,
            remaining_s=remaining,
        )

    async def _press(self, entity_id: str) -> bool:
        # Prefer an explicit adapter method when available (handy for tests and future
        # refactors), but the current HassClient already exposes its authenticated
        # aiohttp session. Keep the actual service call here so the lease can be added
        # without broadening the generic power-supply API surface.
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

    async def renew(self, *, force: bool = False) -> EdgeLeaseState:
        if not force and not self.renewal_due():
            state = await self.read_state()
            if not state.armed or not self._fresh_modbus(state):
                raise EdgeSafetyLeaseError("edge lease is not healthy between renewals")
            return state

        before = await self.read_state()
        if not self._fresh_modbus(before):
            raise EdgeSafetyLeaseError(
                f"RD6018 Modbus is stale at edge ({before.modbus_age_s:.1f}s)"
            )
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
                and latest.generation != before.generation
                and self._fresh_modbus(latest)
                and (
                    latest.remaining_s is None
                    or latest.remaining_s > self.config.renew_interval_s
                )
            ):
                self._last_ack_monotonic = self._monotonic()
                return latest

        raise EdgeSafetyLeaseError(
            "edge lease renewal was not positively acknowledged by generation/readback"
        )

    async def arm(self) -> EdgeLeaseState:
        return await self.renew(force=True)

    async def renew_if_due(self) -> EdgeLeaseState:
        return await self.renew(force=False)

    async def disarm(self) -> bool:
        # OFF has already been verified by the caller before this is invoked. A failed
        # disarm therefore cannot make the power path unsafe; it intentionally leaves
        # the edge lease armed, which only causes additional local OFF attempts.
        if not await self._press(self.config.disarm_entity):
            return False
        attempts = max(1, int(self.config.ack_attempts))
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(max(0.0, self.config.ack_delay_s))
            try:
                state = await self.read_state()
            except EdgeSafetyLeaseError:
                continue
            if not state.armed:
                self._last_ack_monotonic = None
                return True
        return False
