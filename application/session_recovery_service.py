"""Application ownership for one managed-session recovery cycle and its execution.

The runtime supplies one fresh observation while holding the production owner
lock, then dispatches the ordered log/notification effects returned here.
Physical writes remain on the existing ExecutionPort.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from runtime.charge.controller_state import (
    mark_startup_observation_seen,
    set_last_known_output_on,
)
from runtime.charge.link_session_recovery import (
    RecoveryAction,
    RecoveryAuthorizationInput,
    RecoveryRoute,
    RecoveryRouteInput,
    authorize_recovery_action,
    choose_recovery_route,
)
from .session_recovery_guard import SessionRecoveryGuard


@dataclass(frozen=True)
class RecoveryExecutionResult:
    """Explicit result for the physical prerequisites of one restore route.

    ``output_confirmed`` is None when the route deliberately did not verify
    Output (route C normal); an earlier telemetry observation is not proof.
    """

    confirmed: bool
    failed_step: str | None = None
    output_confirmed: bool | None = None


@dataclass(frozen=True)
class SessionRecoveryObservation:
    """Ephemeral telemetry snapshot consumed by one locked recovery cycle."""

    output_on: bool
    current_a: float
    temperature_available: bool
    battery_voltage_v: float
    temperature_c: float
    amp_hours: float
    is_cv: bool
    is_cc: bool
    input_voltage_v: float


@dataclass(frozen=True)
class SessionRecoveryEffect:
    """Ordered runtime sink operation produced by the application use case."""

    kind: str
    message: str
    log_arguments: tuple[Any, ...] = ()
    critical: bool | None = None
    event_stage: str | None = None
    event_voltage_v: float | None = None
    event_current_a: float | None = None
    event_temperature_c: float | None = None
    event_ah: float | None = None


@dataclass(frozen=True)
class SessionRecoveryCycleResult:
    route: RecoveryRoute
    effects: tuple[SessionRecoveryEffect, ...]
    output_on: bool
    last_checkpoint_time: float | None = None


class SessionRecoveryPort(Protocol):
    async def program_voltage(self, value_v: float) -> bool: ...
    async def program_current(self, value_a: float) -> bool: ...
    async def request_verified_off(self) -> bool: ...
    async def request_verified_on(self) -> bool: ...


class SessionRecoveryService:
    def __init__(
        self,
        execution_port: SessionRecoveryPort,
        cap_current: Callable[[float], float],
        guard: SessionRecoveryGuard | None = None,
    ) -> None:
        self._port = execution_port
        self._cap_current = cap_current
        self._guard = guard or getattr(execution_port, "session_recovery_guard", None) or SessionRecoveryGuard()

    def _failed(self, step: str) -> None:
        self._guard.quarantine(step)

    def _allowed(self) -> bool:
        return self._guard.may_run_automatic_control()

    @staticmethod
    async def run_cycle(
        *,
        observation: SessionRecoveryObservation,
        controller: Any,
        live: dict[str, Any],
        session_path: str,
        minimum_input_voltage_v: float,
        execution_port_getter: Callable[[], SessionRecoveryPort],
        cap_current: Callable[[float], float],
    ) -> SessionRecoveryCycleResult:
        """Run one existing restored-session route inside the caller's owner lock.

        Runtime effects are returned in order so the runtime remains the owner
        of logging, notifications and its shared checkpoint timestamp.
        """
        cold_start = not getattr(
            controller, "_d125_startup_observation_seen", False
        )
        mark_startup_observation_seen(controller)
        route = choose_recovery_route(RecoveryRouteInput(
            was_unavailable=controller._was_unavailable,
            stage=controller.current_stage,
            idle_stage=controller.STAGE_IDLE,
            done_stage=controller.STAGE_DONE,
            cooling_stage=getattr(controller, "STAGE_COOLING", "__no_cooling__"),
            output_on=observation.output_on,
            current_a=observation.current_a,
            temperature_available=observation.temperature_available,
        ))

        # Match the old lazy lookup: only create execution choreography for a
        # selected route, then resolve the current guard from the live port.
        recovery_execution = (
            SessionRecoveryService(execution_port_getter(), cap_current)
            if route is not RecoveryRoute.NONE
            else None
        )
        recovery_guard = execution_port_getter().session_recovery_guard
        effects: list[SessionRecoveryEffect] = []
        output_on = observation.output_on
        checkpoint_time = None

        def effect(kind: str, message: str, **kwargs: Any) -> None:
            effects.append(SessionRecoveryEffect(kind, message, **kwargs))

        def restore_effect() -> SessionRecoveryEffect:
            return SessionRecoveryEffect(
                "event", "RESTORE", event_stage=controller.current_stage,
                event_voltage_v=observation.battery_voltage_v,
                event_current_a=observation.current_a,
                event_temperature_c=observation.temperature_c,
                event_ah=observation.amp_hours,
            )

        def correct_restore_times() -> None:
            from runtime.startup_recovery import apply_restore_time_corrections

            apply_restore_time_corrections(controller, live, now_s=time.time())

        def restore_allows_enable() -> bool:
            from runtime.charge.persistence import restore_allows_auto_enable

            return restore_allows_auto_enable(controller)

        if recovery_guard.quarantined:
            effect(
                "warning",
                "D084 session recovery quarantine remains active (%s); "
                "automatic restore and controller tick are suppressed",
                log_arguments=(str(recovery_guard.state.reason),),
            )
        elif route is RecoveryRoute.ACTIVE_LINK and authorize_recovery_action(
            RecoveryAuthorizationInput(
                route=route,
                restored=True,
                auto_enable_authorized=True,
                cold_start=cold_start,
                safe_wait=False,
                input_voltage_ok=(
                    observation.input_voltage_v >= minimum_input_voltage_v
                ),
            )
        ) is RecoveryAction.REENABLE_ACTIVE:
            uv, ui = controller._get_target_v_i(observation.temperature_c)
            enabled = await recovery_execution.reenable_active(uv, ui)
            if enabled:
                output_on = True
                set_last_known_output_on(controller, True)
                correct_restore_times()
                checkpoint_time = time.time()
                effects.append(restore_effect())
                effect(
                    "notify",
                    "✅ Связь восстановлена, заряд продолжен с текущего этапа.",
                    critical=False,
                )
                effect(
                    "info", "Active session resumed after link recovery: %s",
                    log_arguments=(controller.current_stage,),
                )
            else:
                reason = recovery_guard.state.reason or "verified_on"
                effect(
                    "warning",
                    "D084 quarantined active session restore (%s); physical Output state is unknown",
                    log_arguments=(reason,),
                )
                effect(
                    "notify",
                    "⚠️ Восстановление не подтверждено; автоматическое управление "
                    "приостановлено, состояние Output неизвестно. Проверьте оборудование.",
                )
        elif not recovery_guard.quarantined and route is RecoveryRoute.IDLE_LINK:
            ok, msg = controller.try_restore_session(
                observation.battery_voltage_v,
                observation.current_a,
                observation.amp_hours,
                output_is_on=observation.output_on,
                is_cv=observation.is_cv,
                is_cc=observation.is_cc,
            )
            if ok and msg:
                correct_restore_times()
                action = authorize_recovery_action(RecoveryAuthorizationInput(
                    route=route,
                    restored=True,
                    auto_enable_authorized=restore_allows_enable(),
                    cold_start=cold_start,
                    safe_wait=controller.current_stage == controller.STAGE_SAFE_WAIT,
                    input_voltage_ok=(
                        observation.input_voltage_v >= minimum_input_voltage_v
                    ),
                ))
                if action is not RecoveryAction.SKIP:
                    if action is RecoveryAction.SAFE_WAIT_OFF:
                        uv, ui = controller._safe_wait_target_v, controller._safe_wait_target_i
                    else:
                        uv, ui = controller._get_target_v_i(observation.temperature_c)
                    result = await recovery_execution.restore_idle_link(
                        uv, ui, safe_wait=action is RecoveryAction.SAFE_WAIT_OFF
                    )
                    if not result.confirmed:
                        effect(
                            "warning",
                            "Session restore execution was not confirmed (%s); physical Output state is unknown",
                            log_arguments=(str(result.failed_step),),
                        )
                        effect(
                            "notify",
                            "⚠️ Действие восстановления не подтверждено "
                            f"({result.failed_step}); состояние Output неизвестно. "
                            "Проверьте состояние оборудования.",
                        )
                    else:
                        checkpoint_time = time.time()
                        effects.append(restore_effect())
                        effect(
                            "notify",
                            "✅ Связь восстановлена, действие подтверждено.\r\n" + (msg or ""),
                            critical=False,
                        )
                        effect(
                            "info", "Session restored after link recovery: %s",
                            log_arguments=(controller.current_stage,),
                        )
                else:
                    if observation.input_voltage_v < minimum_input_voltage_v:
                        effect(
                            "notify",
                            f"⚠️ Низкое входное напряжение ({observation.input_voltage_v:.0f} В < "
                            f"{minimum_input_voltage_v:.0f} В). Включите заряд вручную после проверки питания.",
                        )
                    effect("info", "Restore skipped: input_voltage")
            elif observation.output_on and observation.current_a > 0.05:
                effect(
                    "notify",
                    "⚠️ Связь восстановлена, но сессии нет (или старше 24 ч). "
                    f"Выход включён ({observation.current_a:.2f} А). Нажмите Остановить или запустите заряд заново.",
                )
                effect(
                    "warning", "Link restored but no session; output still on I=%.2fA",
                    log_arguments=(observation.current_a,),
                )

        if (
            not recovery_guard.quarantined
            and route is RecoveryRoute.IDLE_OUTPUT_ON
            and os.path.isfile(session_path)
        ):
            ok, msg = controller.try_restore_session(
                observation.battery_voltage_v,
                observation.current_a,
                observation.amp_hours,
                output_is_on=observation.output_on,
                is_cv=observation.is_cv,
                is_cc=observation.is_cc,
            )
            if ok and msg:
                correct_restore_times()
                action = authorize_recovery_action(RecoveryAuthorizationInput(
                    route=route,
                    restored=True,
                    auto_enable_authorized=restore_allows_enable(),
                    cold_start=cold_start,
                    safe_wait=controller.current_stage == controller.STAGE_SAFE_WAIT,
                    input_voltage_ok=(
                        observation.input_voltage_v >= minimum_input_voltage_v
                    ),
                ))
                if action is not RecoveryAction.SKIP:
                    if action is RecoveryAction.SAFE_WAIT_OFF:
                        uv, ui = controller._safe_wait_target_v, controller._safe_wait_target_i
                    else:
                        uv, ui = controller._get_target_v_i(observation.temperature_c)
                    result = await recovery_execution.restore_output_on(
                        uv, ui, safe_wait=action is RecoveryAction.SAFE_WAIT_OFF
                    )
                    if not result.confirmed:
                        effect(
                            "warning",
                            "Already-on session restore was not confirmed (%s); physical Output state is unknown",
                            log_arguments=(str(result.failed_step),),
                        )
                        effect(
                            "notify",
                            "⚠️ Действие восстановления не подтверждено "
                            f"({result.failed_step}); состояние Output неизвестно. "
                            "Проверьте состояние оборудования.",
                        )
                    else:
                        checkpoint_time = time.time()
                        effects.append(restore_effect())
                        effect(
                            "notify",
                            "✅ Сессия восстановлена; параметры применены. "
                            "Output ON отдельно не подтверждался.",
                            critical=False,
                        )
                        effect(
                            "info",
                            "Session restore parameters applied (Output was not re-confirmed): %s",
                            log_arguments=(controller.current_stage,),
                        )
                else:
                    effect(
                        "debug",
                        "Restore (output on, idle) skipped: allow=%s input_v=%.0f",
                        log_arguments=(
                            "False" if action is RecoveryAction.SKIP else "True",
                            observation.input_voltage_v,
                        ),
                    )
            else:
                effect(
                    "debug",
                    "Restore (output on, idle): try_restore_session returned ok=%s "
                    "(нет файла или сессия старше 24 ч)",
                    log_arguments=(str(ok),),
                )

        return SessionRecoveryCycleResult(
            route=route,
            effects=tuple(effects),
            output_on=output_on,
            last_checkpoint_time=checkpoint_time,
        )

    async def reenable_active(self, voltage_v: float, current_a: float) -> bool:
        """Reapply a lost active session; success means verified ON."""
        if not self._allowed():
            return False
        try:
            capped_current_a = self._cap_current(current_a)
            if not await self._port.program_voltage(voltage_v):
                self._failed("voltage")
                return False
            if not await self._port.program_current(capped_current_a):
                self._failed("current")
                return False
            enabled = await self._port.request_verified_on()
            if not enabled:
                self._failed("verified_on")
            return enabled
        except Exception:
            self._failed("execution_exception")
            raise

    async def restore_idle_link(
        self, voltage_v: float, current_a: float, *, safe_wait: bool
    ) -> RecoveryExecutionResult:
        """Restore lost-link IDLE only through positively accepted prerequisites."""
        if not self._allowed():
            return RecoveryExecutionResult(False, "session_recovery_quarantined")
        try:
            capped_current_a = self._cap_current(current_a)
            if not await self._port.program_voltage(voltage_v):
                self._failed("voltage")
                return RecoveryExecutionResult(False, "voltage")
            if not await self._port.program_current(capped_current_a):
                self._failed("current")
                return RecoveryExecutionResult(False, "current")
            if safe_wait:
                off = await self._port.request_verified_off()
                if not off:
                    self._failed("verified_off")
                return RecoveryExecutionResult(bool(off), None if off else "verified_off", False if off else None)
            on = await self._port.request_verified_on()
            if not on:
                self._failed("verified_on")
            return RecoveryExecutionResult(bool(on), None if on else "verified_on", bool(on) if on else None)
        except Exception:
            self._failed("execution_exception")
            raise

    async def restore_output_on(
        self, voltage_v: float, current_a: float, *, safe_wait: bool
    ) -> RecoveryExecutionResult:
        """Restore setpoints without treating prior Output telemetry as confirmation."""
        if not self._allowed():
            return RecoveryExecutionResult(False, "session_recovery_quarantined")
        try:
            capped_current_a = self._cap_current(current_a)
            if safe_wait:
                off = await self._port.request_verified_off()
                if not off:
                    self._failed("verified_off")
                    return RecoveryExecutionResult(False, "verified_off")
            if not await self._port.program_voltage(voltage_v):
                self._failed("voltage")
                return RecoveryExecutionResult(False, "voltage", False if safe_wait else None)
            if not await self._port.program_current(capped_current_a):
                self._failed("current")
                return RecoveryExecutionResult(False, "current", False if safe_wait else None)
            return RecoveryExecutionResult(True, output_confirmed=False if safe_wait else None)
        except Exception:
            self._failed("execution_exception")
            raise


__all__ = [
    "RecoveryExecutionResult",
    "SessionRecoveryCycleResult",
    "SessionRecoveryEffect",
    "SessionRecoveryObservation",
    "SessionRecoveryService",
]
