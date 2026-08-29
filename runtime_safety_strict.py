from __future__ import annotations

import os
from typing import Any, Optional

from config import TEMP_INT_PRECRITICAL
from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseError
from runtime_safety import (
    RuntimeSafetyError,
    RuntimeSafetyGuard,
    _binary,
    _finite,
)


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}


class StrictRuntimeSafetyGuard(RuntimeSafetyGuard):
    """Final production hardening over the generic runtime safety guard.

    In addition to the normal live checks, production output is protected by a
    renewable lease implemented on the ESPHome node physically connected to RD6018.
    The bot renews it every 10 minutes; the edge node has a 30 minute TTL. If the bot,
    HA, Wi-Fi/API path, or Python process disappears, the edge node turns RD6018 OFF
    locally instead of allowing a high-voltage stage to run indefinitely.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        explicit_lease = getattr(app, "edge_safety_lease", None)
        production_adapter = (
            callable(getattr(self.hass, "get_state", None))
            and bool(getattr(self.hass, "base_url", None))
        )
        if explicit_lease is None and production_adapter:
            explicit_lease = EdgeSafetyLease(self.hass)
            app.edge_safety_lease = explicit_lease

        self.edge_safety_lease = explicit_lease
        # Default is deliberately fail-closed for the real HassClient. Unit-test and
        # non-HA adapters without the required primitives are not silently promoted
        # into production; they simply do not claim this hardware boundary exists.
        self.edge_lease_enforced = _env_enabled("RD6018_EDGE_LEASE_REQUIRED", True) and (
            production_adapter or explicit_lease is not None
        )

    async def _arm_edge_lease(self) -> None:
        if not self.edge_lease_enforced:
            return
        if self.edge_safety_lease is None:
            raise RuntimeSafetyError("edge safety lease is required but unavailable")
        try:
            await self.edge_safety_lease.arm()
        except Exception as exc:
            raise RuntimeSafetyError(f"edge safety lease arm failed: {exc}") from exc

    async def _renew_edge_lease_or_fail(self, *, output_state: bool) -> None:
        if not self.edge_lease_enforced:
            return
        if self.edge_safety_lease is None:
            await self._fail_closed(
                "edge_lease_missing",
                "локальный RD6018 safety lease обязателен, но недоступен",
                output_state=output_state,
            )
        try:
            await self.edge_safety_lease.renew_if_due()
        except Exception as exc:
            await self._fail_closed(
                "edge_lease_lost",
                f"локальный RD6018 safety lease не подтверждён ({exc})",
                output_state=output_state,
            )

    async def _disarm_edge_lease_best_effort(self) -> None:
        if self.edge_safety_lease is None:
            return
        try:
            ok = bool(await self.edge_safety_lease.disarm())
        except Exception:
            ok = False
        if not ok:
            # Output is already physically confirmed OFF before this helper is called.
            # Leaving the lease armed is fail-safe: the edge node will only keep issuing
            # more OFF commands. Surface the maintenance problem but do not turn a safe
            # shutdown into an unsafe exception.
            self._notify(
                "edge_lease_disarm_failed",
                "⚠️ RD6018 уже подтверждён OFF, но локальный safety lease не удалось "
                "снять. Он останется fail-safe armed и продолжит требовать OFF.",
            )

    async def get_all_live(self) -> dict[str, Any]:
        live = await super().get_all_live()
        output_state = _binary(live.get("switch"))

        # Do not rely exclusively on the data_logger's next action dispatch for a real
        # hardware trip. Request OFF here too, then return the original trip snapshot
        # so the legacy handler can still record OVP/OCP as the session-ending reason.
        if output_state is True and (
            _binary(live.get("ovp_triggered")) is True
            or _binary(live.get("ocp_triggered")) is True
        ):
            await self._ensure_output_off("hardware OVP/OCP protection trip")
            return live

        temp_int = _finite(live.get("temp_int"))
        if output_state is True and temp_int is not None and temp_int >= float(TEMP_INT_PRECRITICAL):
            await self._fail_closed(
                "psu_temperature_high",
                f"температура RD6018 {temp_int:.1f}°C >= {float(TEMP_INT_PRECRITICAL):.1f}°C",
                output_state=True,
            )

        if output_state is True and self.controller_active:
            await self._renew_edge_lease_or_fail(output_state=True)
        return live

    async def turn_on(self, entity_id: Optional[str] = None) -> bool:
        # Preserve the stronger latched-OFF invariant before doing any new work.
        if self._off_unconfirmed:
            return await super().turn_on(entity_id)
        if not self.controller_active:
            state = await self._output_state_raw()
            if state is True:
                await self._ensure_output_off(
                    "turn-on requested without an active controller session",
                    entity_id,
                )
            raise RuntimeSafetyError("turn-on blocked: no active controller session")

        # Arm the local dead-man timer before any path is allowed to energize RD6018.
        # A missing ESPHome package/entity therefore blocks ON rather than degrading to
        # an ordinary network watchdog that cannot stop the PSU after communications die.
        await self._arm_edge_lease()
        try:
            enabled = await super().turn_on(entity_id)
        except Exception:
            if await self._output_state_raw() is False:
                await self._disarm_edge_lease_best_effort()
            raise
        if not enabled and await self._output_state_raw() is False:
            await self._disarm_edge_lease_best_effort()
        return enabled

    async def turn_off(self, entity_id: Optional[str] = None) -> bool:
        confirmed = await super().turn_off(entity_id)
        if confirmed:
            await self._disarm_edge_lease_best_effort()
        return confirmed

    async def set_ovp(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        if output_state is True and requested is not None:
            live = await self._raw_live()
            set_v = _finite(live.get("set_voltage"))
            if set_v is None:
                await self._ensure_output_off("OVP change attempted without live voltage readback")
                raise RuntimeSafetyError("OVP change blocked: live voltage setpoint unavailable")
            if requested + self.READBACK_TOLERANCE < set_v + self.PROTECTION_MARGIN:
                await self._ensure_output_off(
                    f"OVP {requested:.3f}V would no longer protect live voltage {set_v:.3f}V"
                )
                raise RuntimeSafetyError("OVP change blocked: active voltage envelope would be unprotected")
        return await super().set_ovp(value)

    async def set_ocp(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        if output_state is True and requested is not None:
            live = await self._raw_live()
            set_i = _finite(live.get("set_current"))
            if set_i is None:
                await self._ensure_output_off("OCP change attempted without live current readback")
                raise RuntimeSafetyError("OCP change blocked: live current setpoint unavailable")
            if requested + self.READBACK_TOLERANCE < set_i + self.PROTECTION_MARGIN:
                await self._ensure_output_off(
                    f"OCP {requested:.3f}A would no longer protect live current {set_i:.3f}A"
                )
                raise RuntimeSafetyError("OCP change blocked: active current envelope would be unprotected")
        return await super().set_ocp(value)


def install_strict_runtime_safety(app: Any) -> StrictRuntimeSafetyGuard:
    existing = getattr(app.hass, "_runtime_safety_guard", None)
    if isinstance(existing, StrictRuntimeSafetyGuard):
        return existing
    if existing is not None:
        raise RuntimeError("runtime safety guard was installed before strict production guard")

    guard = StrictRuntimeSafetyGuard(app)
    guard.install()
    app.runtime_safety_guard = guard
    return guard
