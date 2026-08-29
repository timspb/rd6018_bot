from __future__ import annotations

from typing import Any, Optional

from config import TEMP_INT_PRECRITICAL
from runtime_safety import (
    RuntimeSafetyError,
    RuntimeSafetyGuard,
    _binary,
    _finite,
)


class StrictRuntimeSafetyGuard(RuntimeSafetyGuard):
    """Final production hardening over the generic runtime safety guard.

    These invariants are intentionally enforced at the shared HassClient boundary,
    not only in controller call sites:

    * an idle controller cannot energize the output;
    * PSU over-temperature is an immediate live fail-close;
    * OVP/OCP may not be lowered below the already programmed live V/I envelope.

    That makes a stale UI callback, a future controller regression, or a caller that
    ignores setter return values unable to silently remove the active hardware guard.
    """

    async def get_all_live(self) -> dict[str, Any]:
        live = await super().get_all_live()
        output_state = _binary(live.get("switch"))
        temp_int = _finite(live.get("temp_int"))
        if output_state is True and temp_int is not None and temp_int >= float(TEMP_INT_PRECRITICAL):
            await self._fail_closed(
                "psu_temperature_high",
                f"температура RD6018 {temp_int:.1f}°C >= {float(TEMP_INT_PRECRITICAL):.1f}°C",
                output_state=True,
            )
        return live

    async def turn_on(self, entity_id: Optional[str] = None) -> bool:
        if not self.controller_active:
            state = await self._output_state_raw()
            if state is True:
                await self._ensure_output_off(
                    "turn-on requested without an active controller session",
                    entity_id,
                )
            raise RuntimeSafetyError("turn-on blocked: no active controller session")
        return await super().turn_on(entity_id)

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
