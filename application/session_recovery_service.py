"""Execution choreography for restoring a managed charging session.

Target selection, restore authority, persistence and user-facing effects stay
with the runtime. This use case sends the approved targets through the existing
execution port while its caller holds the production owner lock.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol


class SessionRecoveryPort(Protocol):
    async def program_voltage(self, value_v: float) -> bool: ...
    async def program_current(self, value_a: float) -> bool: ...
    async def request_verified_off(self) -> bool: ...
    async def request_verified_on(self) -> bool: ...


class SessionRecoveryService:
    def __init__(
        self,
        execution_port: SessionRecoveryPort,
        apply_phase_protection: Callable[[float, float], Awaitable[None]],
        cap_current: Callable[[float], float],
    ) -> None:
        self._port = execution_port
        self._apply_phase_protection = apply_phase_protection
        self._cap_current = cap_current

    async def reenable_active(self, voltage_v: float, current_a: float) -> bool:
        """Reapply a lost active session; success means verified ON."""
        await self._apply_phase_protection(voltage_v, current_a)
        await self._port.program_voltage(voltage_v)
        await self._port.program_current(self._cap_current(current_a))
        return await self._port.request_verified_on()

    async def restore_idle_link(
        self, voltage_v: float, current_a: float, *, safe_wait: bool
    ) -> None:
        """Restore lost-link IDLE; preserve legacy ignored execution results."""
        await self._apply_phase_protection(voltage_v, current_a)
        await self._port.program_voltage(voltage_v)
        await self._port.program_current(self._cap_current(current_a))
        if safe_wait:
            await self._port.request_verified_off()
        else:
            # Historical route B did not branch on this result.
            await self._port.request_verified_on()

    async def restore_output_on(
        self, voltage_v: float, current_a: float, *, safe_wait: bool
    ) -> None:
        """Adopt restored setpoints while Output is already ON; never request ON."""
        await self._apply_phase_protection(voltage_v, current_a)
        if safe_wait:
            await self._port.request_verified_off()
        await self._port.program_voltage(voltage_v)
        await self._port.program_current(self._cap_current(current_a))


__all__ = ["SessionRecoveryService"]
