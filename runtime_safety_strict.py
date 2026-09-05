from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from config import TEMP_INT_PRECRITICAL
from edge_safety_lease import EdgeSafetyLease
from runtime_safety import (
    RuntimeSafetyError,
    RuntimeSafetyGuard,
    _binary,
    _finite,
    logger,
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
    The bot renews it every 5 minutes; the accepted V2 edge contract has a 15 minute
    TTL. If the bot, HA, Wi-Fi/API path, or Python process disappears, the edge node
    turns RD6018 OFF locally instead of allowing a high-voltage stage to run
    indefinitely.
    """

    TRANSITION_SETTLE_TIMEOUT_S = 6.5
    TRANSITION_SETTLE_POLL_S = 0.20
    CURRENT_SETTLE_MARGIN_A = 0.05
    VOLTAGE_SETTLE_MARGIN_V = 0.05

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
        if ok:
            logger.info("Edge safety lease disarm confirmed")
            return
        self._notify(
            "edge_lease_disarm_failed",
            "⚠️ RD6018 уже подтверждён OFF, но локальный safety lease не удалось "
            "снять. Он останется fail-safe armed и продолжит требовать OFF.",
        )

    async def get_all_live(self) -> dict[str, Any]:
        live = await super().get_all_live()
        output_state = _binary(live.get("switch"))
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
        await self._arm_edge_lease()
        try:
            enabled = await super().turn_on(entity_id)
        except Exception:
            # super().turn_on() normally performs its own cleanup, but an exception in
            # the *post-enable* telemetry read used to escape after the physical ON.
            # Never assume an exception means the output stayed OFF: positively prove
            # OFF here before returning control to the caller.
            state = await self._output_state_raw()
            if state is not False:
                await self._ensure_output_off(
                    "turn-on path raised before post-enable safety was confirmed",
                    entity_id,
                )
                state = False
            if state is False:
                await self._disarm_edge_lease_best_effort()
            raise
        if not enabled and await self._output_state_raw() is False:
            await self._disarm_edge_lease_best_effort()
        return enabled

    async def turn_off(self, entity_id: Optional[str] = None) -> bool:
        confirmed = await super().turn_off(entity_id)
        if confirmed:
            logger.info("Output OFF verified; edge lease disarm may proceed")
            await self._disarm_edge_lease_best_effort()
        return confirmed

    async def _wait_measured_below(
        self,
        *,
        key: str,
        ceiling: float,
        trip_key: str,
    ) -> bool:
        """Wait for measured hardware state, not only command/setpoint readback."""
        poll_s = max(0.001, float(self.TRANSITION_SETTLE_POLL_S))
        timeout_s = max(0.0, float(self.TRANSITION_SETTLE_TIMEOUT_S))
        attempts = max(1, int(timeout_s / poll_s) + 1)
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(poll_s)
            try:
                live = await self._raw_live()
            except Exception:
                continue
            if _binary(live.get("switch")) is False:
                return False
            if _binary(live.get(trip_key)) is True:
                return False
            measured = _finite(live.get(key))
            if measured is not None and measured <= float(ceiling):
                return True
        return False

    def _stage_target(self, live: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        target_fn = getattr(self.app.charge_controller, "_get_target_v_i", None)
        if not callable(target_fn):
            return None, None
        temp_ext = _finite(live.get("temp_ext"))
        try:
            target_v, target_i = target_fn(temp_ext)
        except Exception:
            return None, None
        return _finite(target_v), _finite(target_i)

    async def _require_managed_live_write(
        self,
        output_state: Optional[bool],
        action: str,
    ) -> None:
        if output_state is not True or self.controller_active:
            return
        await self._ensure_output_off(
            f"{action} requested while Output ON without a managed controller session"
        )
        raise RuntimeSafetyError(
            f"{action} blocked: live setpoint/protection writes require a managed session"
        )

    async def _precondition_current_before_voltage_raise(
        self,
        requested_voltage: float,
        live: dict[str, Any],
    ) -> None:
        live_set_v = _finite(live.get("set_voltage"))
        live_set_i = self._current_evidence(live)
        if live_set_v is None or live_set_i is None:
            await self._ensure_output_off(
                "voltage transition attempted without live setpoint readback"
            )
            raise RuntimeSafetyError(
                "voltage transition blocked: live V/I setpoint unavailable"
            )
        if requested_voltage <= live_set_v + self.READBACK_TOLERANCE:
            return
        _target_v, target_i = self._stage_target(live)
        if target_i is None or target_i <= 0:
            await self._ensure_output_off(
                "voltage transition could not resolve a valid current-stage target"
            )
            raise RuntimeSafetyError(
                "voltage transition blocked: current-stage target unavailable"
            )
        if target_i + self.READBACK_TOLERANCE >= live_set_i:
            return
        await super().set_current(target_i)
        if not await self._wait_measured_below(
            key="current",
            ceiling=target_i + self.CURRENT_SETTLE_MARGIN_A,
            trip_key="ocp_triggered",
        ):
            await self._ensure_output_off(
                "current did not settle before live voltage increase"
            )
            raise RuntimeSafetyError(
                "voltage transition blocked: measured current did not settle"
            )

    async def _precondition_voltage_before_ovp_tighten(
        self,
        requested_ovp: float,
        live: dict[str, Any],
    ) -> dict[str, Any]:
        """Lower Vset first when a paired live OVP decrease needs real margin."""
        current_ovp = _finite(live.get("ovp"))
        live_set_v = _finite(live.get("set_voltage"))
        if current_ovp is None or live_set_v is None:
            return live
        if requested_ovp + self.READBACK_TOLERANCE >= current_ovp:
            return live
        # Protection geometry is physical, not a readback comparison. Do not let the
        # 60 mV readback tolerance erase the required OVP margin over the old Vset.
        if requested_ovp >= live_set_v + self.PROTECTION_MARGIN:
            return live
        target_v, _target_i = self._stage_target(live)
        if (
            target_v is None
            or target_v <= 0
            or target_v + self.PROTECTION_MARGIN > requested_ovp
            or target_v >= live_set_v - self.READBACK_TOLERANCE
        ):
            return live
        await super().set_voltage(target_v)
        if not await self._wait_measured_below(
            key="voltage",
            ceiling=max(0.0, requested_ovp - self.VOLTAGE_SETTLE_MARGIN_V),
            trip_key="ovp_triggered",
        ):
            await self._ensure_output_off(
                "output voltage did not settle before OVP tightening"
            )
            raise RuntimeSafetyError(
                "OVP change blocked: measured voltage did not settle"
            )
        return await self._raw_live()

    async def set_voltage(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        await self._require_managed_live_write(output_state, "voltage write")
        if output_state is True and requested is not None:
            live = await self._raw_live()
            await self._precondition_current_before_voltage_raise(requested, live)
        return await super().set_voltage(value)

    async def set_current(self, value: float) -> bool:
        output_state = await self._output_state_raw()
        await self._require_managed_live_write(output_state, "current write")
        return await super().set_current(value)

    async def set_ovp(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        await self._require_managed_live_write(output_state, "OVP write")
        if output_state is True and requested is not None:
            live = await self._raw_live()
            live = await self._precondition_voltage_before_ovp_tighten(requested, live)
            set_v = _finite(live.get("set_voltage"))
            if set_v is None:
                await self._ensure_output_off("OVP change attempted without live voltage readback")
                raise RuntimeSafetyError("OVP change blocked: live voltage setpoint unavailable")
            if requested + self.READBACK_TOLERANCE < set_v + self.PROTECTION_MARGIN:
                await self._ensure_output_off(
                    f"OVP {requested:.3f}V would no longer protect live voltage {set_v:.3f}V"
                )
                raise RuntimeSafetyError("OVP change blocked: active voltage envelope would be unprotected")
            current_ovp = _finite(live.get("ovp"))
            measured_v = _finite(live.get("voltage"))
            if (
                current_ovp is not None
                and requested + self.READBACK_TOLERANCE < current_ovp
                and measured_v is not None
                and measured_v > requested - self.VOLTAGE_SETTLE_MARGIN_V
            ):
                if not await self._wait_measured_below(
                    key="voltage",
                    ceiling=requested - self.VOLTAGE_SETTLE_MARGIN_V,
                    trip_key="ovp_triggered",
                ):
                    await self._ensure_output_off(
                        "output voltage did not settle before OVP tightening"
                    )
                    raise RuntimeSafetyError(
                        "OVP change blocked: measured voltage did not settle"
                    )
        return await super().set_ovp(value)

    async def set_ocp(self, value: float) -> bool:
        requested = _finite(value)
        output_state = await self._output_state_raw()
        await self._require_managed_live_write(output_state, "OCP write")
        if output_state is True and requested is not None:
            live = await self._raw_live()
            set_i = self._current_evidence(live)
            if set_i is None:
                await self._ensure_output_off("OCP change attempted without live current readback")
                raise RuntimeSafetyError("OCP change blocked: live current setpoint unavailable")
            if requested + self.READBACK_TOLERANCE < set_i + self.PROTECTION_MARGIN:
                await self._ensure_output_off(
                    f"OCP {requested:.3f}A would no longer protect live current {set_i:.3f}A"
                )
                raise RuntimeSafetyError("OCP change blocked: active current envelope would be unprotected")
            current_ocp = _finite(live.get("ocp"))
            measured_i = _finite(live.get("current"))
            settle_ceiling = max(0.0, requested - self.PROTECTION_MARGIN)
            if (
                current_ocp is not None
                and requested + self.READBACK_TOLERANCE < current_ocp
                and measured_i is not None
                and measured_i > settle_ceiling
            ):
                if not await self._wait_measured_below(
                    key="current",
                    ceiling=settle_ceiling,
                    trip_key="ocp_triggered",
                ):
                    await self._ensure_output_off(
                        "measured current did not settle before OCP tightening"
                    )
                    raise RuntimeSafetyError(
                        "OCP change blocked: measured current did not settle"
                    )
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
