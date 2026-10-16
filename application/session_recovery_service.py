"""Execution choreography for restoring a managed charging session.

Target selection, restore authority, persistence and user-facing effects stay
with the runtime. This use case sends the approved targets through the existing
execution port while its caller holds the production owner lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


@dataclass(frozen=True)
class RecoveryExecutionResult:
    """Explicit result for the physical prerequisites of one restore route.

    ``output_confirmed`` is None when the route deliberately did not verify
    Output (route C normal); an earlier telemetry observation is not proof.
    """

    confirmed: bool
    failed_step: str | None = None
    output_confirmed: bool | None = None


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
        if not await self._port.program_voltage(voltage_v):
            return False
        if not await self._port.program_current(self._cap_current(current_a)):
            return False
        return await self._port.request_verified_on()

    async def restore_idle_link(
        self, voltage_v: float, current_a: float, *, safe_wait: bool
    ) -> RecoveryExecutionResult:
        """Restore lost-link IDLE only through positively accepted prerequisites."""
        await self._apply_phase_protection(voltage_v, current_a)
        if not await self._port.program_voltage(voltage_v):
            return RecoveryExecutionResult(False, "voltage")
        if not await self._port.program_current(self._cap_current(current_a)):
            return RecoveryExecutionResult(False, "current")
        if safe_wait:
            off = await self._port.request_verified_off()
            return RecoveryExecutionResult(bool(off), None if off else "verified_off", False if off else None)
        on = await self._port.request_verified_on()
        return RecoveryExecutionResult(bool(on), None if on else "verified_on", bool(on) if on else None)

    async def restore_output_on(
        self, voltage_v: float, current_a: float, *, safe_wait: bool
    ) -> RecoveryExecutionResult:
        """Restore setpoints without treating prior Output telemetry as confirmation."""
        await self._apply_phase_protection(voltage_v, current_a)
        if safe_wait:
            off = await self._port.request_verified_off()
            if not off:
                return RecoveryExecutionResult(False, "verified_off")
        if not await self._port.program_voltage(voltage_v):
            return RecoveryExecutionResult(False, "voltage", False if safe_wait else None)
        if not await self._port.program_current(self._cap_current(current_a)):
            return RecoveryExecutionResult(False, "current", False if safe_wait else None)
        return RecoveryExecutionResult(True, output_confirmed=False if safe_wait else None)


__all__ = ["RecoveryExecutionResult", "SessionRecoveryService"]
