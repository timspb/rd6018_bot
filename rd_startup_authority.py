from __future__ import annotations

import asyncio
import contextvars
from typing import Any, Awaitable, Callable, Optional

from runtime_safety import RuntimeSafetyError


class RdStartupAuthorityGate:
    """Keep normal control closed until edge mode and durable startup state agree.

    D065 makes the ESP edge bit authoritative for AUTONOMOUS operation. A transiently
    unavailable edge/HA snapshot at process startup is therefore neither managed nor
    autonomous permission. This outermost production gate prevents ordinary bot actions
    and application/ownership starts until the edge mode is explicit and non-autonomous
    durable recovery has completed.

    Recovery itself may need the already-existing verified-OFF actuator transaction.
    A task-local context variable grants that narrow path without opening normal bot
    commands in parallel. Unknown state never becomes OFF, HANDS_OFF or AUTONOMOUS.
    """

    def __init__(self, app: Any, manager: Any) -> None:
        self.app = app
        self.manager = manager
        self.guard = manager.guard
        self.candidate_autonomous: Optional[bool] = None
        self.reconciliation_complete = False
        self.managed_recovery_complete = False
        self.reconciliation_error = ""
        self._recovery_scope: contextvars.ContextVar[bool] = contextvars.ContextVar(
            "rd_startup_recovery_scope", default=False
        )
        self._install_hass_gate()
        self._install_application_gate()
        self._install_ownership_gate()
        self._install_return_pb_gate()

    @staticmethod
    def parse_explicit(raw: Any) -> Optional[bool]:
        if not isinstance(raw, dict):
            return None
        value = raw.get("autonomous_mode")
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

    @property
    def recovery_scope(self) -> bool:
        return bool(self._recovery_scope.get())

    @property
    def nonautonomous_ready(self) -> bool:
        return bool(self.reconciliation_complete and self.managed_recovery_complete and self.candidate_autonomous is False)

    @property
    def managed_actuation_ready(self) -> bool:
        return bool(self.nonautonomous_ready and getattr(self.manager, "pb_managed", False) and not getattr(self.manager, "edge_autonomous", False))

    def _blocked(self, action: str) -> RuntimeSafetyError:
        if self.candidate_autonomous is True or bool(getattr(self.manager, "edge_autonomous", False)):
            state = "edge AUTONOMOUS"
        elif self.candidate_autonomous is False:
            state = "managed startup recovery incomplete"
        else:
            state = "edge authority unresolved"
        return RuntimeSafetyError(f"{state}: bot {action} is blocked")

    def _install_hass_gate(self) -> None:
        hass = self.app.hass
        if bool(getattr(hass, "_rd_startup_authority_gate_wrapped", False)):
            return
        original_get_all_live = hass.get_all_live
        original_turn_on = hass.turn_on
        original_turn_off = hass.turn_off
        original_set_voltage = hass.set_voltage
        original_set_current = hass.set_current
        original_set_ovp = hass.set_ovp
        original_set_ocp = hass.set_ocp

        async def get_all_live() -> dict[str, Any]:
            if self.nonautonomous_ready:
                return await original_get_all_live()
            raw = await self.guard._raw_live()
            self.manager._observe_edge_mode(raw)
            return raw

        async def guarded(action: str, fn: Callable[..., Awaitable[Any]], *args: Any) -> bool:
            if not self.recovery_scope and not self.managed_actuation_ready:
                raise self._blocked(action)
            return bool(await fn(*args))

        async def turn_on(entity_id: Optional[str] = None) -> bool:
            return await guarded("Output ON", original_turn_on, entity_id)
        async def turn_off(entity_id: Optional[str] = None) -> bool:
            return await guarded("Output OFF", original_turn_off, entity_id)
        async def set_voltage(value: float) -> bool:
            return await guarded("voltage write", original_set_voltage, value)
        async def set_current(value: float) -> bool:
            return await guarded("current write", original_set_current, value)
        async def set_ovp(value: float) -> bool:
            return await guarded("OVP write", original_set_ovp, value)
        async def set_ocp(value: float) -> bool:
            return await guarded("OCP write", original_set_ocp, value)

        hass.get_all_live = get_all_live
        hass.turn_on = turn_on
        hass.turn_off = turn_off
        hass.set_voltage = set_voltage
        hass.set_current = set_current
        hass.set_ovp = set_ovp
        hass.set_ocp = set_ocp
        hass._rd_startup_authority_gate_wrapped = True

    def _install_application_gate(self) -> None:
        controller = getattr(self.app, "charge_controller", None)
        if controller is not None and not bool(getattr(controller, "_rd_startup_authority_start_wrapped", False)):
            original_start = controller.start
            def start(*args: Any, **kwargs: Any) -> Any:
                if not self.managed_actuation_ready:
                    raise self._blocked("automatic charge start")
                return original_start(*args, **kwargs)
            controller.start = start
            controller._rd_startup_authority_start_wrapped = True

        if controller is not None and callable(getattr(controller, "try_restore_session", None)) and not bool(getattr(controller, "_rd_startup_authority_restore_wrapped", False)):
            original_restore = controller.try_restore_session
            def restore(*args: Any, **kwargs: Any) -> Any:
                if not self.managed_actuation_ready:
                    return False, None
                return original_restore(*args, **kwargs)
            controller.try_restore_session = restore
            controller._rd_startup_authority_restore_wrapped = True

        import v2_mix_mode
        if not bool(getattr(v2_mix_mode, "_rd_startup_authority_wrapped", False)):
            original_mix = v2_mix_mode.start_mix_transactional
            async def mix_start(app_arg: Any, event: Any, pending: Any) -> bool:
                installed = getattr(app_arg, "rd_startup_authority_gate", None) is self
                if installed and not self.managed_actuation_ready:
                    raise self._blocked("Mix start")
                return bool(await original_mix(app_arg, event, pending))
            v2_mix_mode.start_mix_transactional = mix_start
            v2_mix_mode._rd_startup_authority_wrapped = True

    def _install_ownership_gate(self) -> None:
        for attr in ("rd_managed_live_adoption", "rd_managed_mix_adoption"):
            coordinator = getattr(self.app, attr, None)
            if coordinator is None or bool(getattr(coordinator, "_rd_startup_authority_adopt_wrapped", False)):
                continue
            original_adopt = coordinator.adopt
            async def adopt(*args: Any, __original=original_adopt, **kwargs: Any) -> bool:
                if not self.nonautonomous_ready:
                    raise self._blocked("live ownership adoption")
                return bool(await __original(*args, **kwargs))
            coordinator.adopt = adopt
            coordinator._rd_startup_authority_adopt_wrapped = True

        observer = getattr(self.app, "rd_live_mix_observer", None)
        if observer is not None and not bool(getattr(observer, "_rd_startup_authority_start_wrapped", False)):
            original_observer_start = observer.start
            async def observer_start(*args: Any, **kwargs: Any) -> Any:
                if not self.nonautonomous_ready:
                    raise self._blocked("HANDS_OFF observer start")
                return await original_observer_start(*args, **kwargs)
            observer.start = observer_start
            observer._rd_startup_authority_start_wrapped = True

    def _install_return_pb_gate(self) -> None:
        original = self.manager.return_pb_control
        async def return_pb_control() -> bool:
            was_explicit_autonomous = bool(self.candidate_autonomous is True or getattr(self.manager, "edge_autonomous", False))
            result = bool(await original())
            if result and was_explicit_autonomous and bool(getattr(self.manager, "pb_managed", False)):
                self.mark_managed_recovered()
            return result
        self.manager.return_pb_control = return_pb_control

    def hold_unresolved(self, reason: str = "edge authority unresolved") -> None:
        self.candidate_autonomous = None
        self.reconciliation_complete = False
        self.managed_recovery_complete = False
        self.reconciliation_error = str(reason)

    def mark_autonomous(self) -> None:
        self.candidate_autonomous = True
        self.reconciliation_complete = True
        self.managed_recovery_complete = False
        self.reconciliation_error = ""
        self.manager._edge_autonomous = True

    def mark_managed_recovered(self) -> None:
        self.candidate_autonomous = False
        self.reconciliation_complete = True
        self.managed_recovery_complete = True
        self.reconciliation_error = ""
        self.manager._edge_autonomous = False

    async def reconcile(self, recover: Callable[[], Awaitable[bool]], *, retry_s: float = 5.0) -> str:
        delay = max(1.0, float(retry_s))
        self.hold_unresolved()
        while True:
            try:
                raw = await self.guard._raw_live()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.hold_unresolved(f"edge authority read failed: {type(exc).__name__}: {exc}")
                await asyncio.sleep(delay)
                continue
            candidate = self.parse_explicit(raw)
            if candidate is None:
                self.hold_unresolved("edge autonomous authority missing/unavailable")
                await asyncio.sleep(delay)
                continue
            self.manager._observe_edge_mode(raw)
            if candidate:
                self.mark_autonomous()
                return "autonomous"
            self.candidate_autonomous = False
            token = self._recovery_scope.set(True)
            try:
                recovered = bool(await recover())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.reconciliation_error = f"managed startup recovery failed: {type(exc).__name__}: {exc}"
                self.reconciliation_complete = False
                return "blocked"
            finally:
                self._recovery_scope.reset(token)
            if not recovered:
                self.reconciliation_error = "managed startup recovery did not prove containment"
                self.reconciliation_complete = False
                return "blocked"
            self.mark_managed_recovered()
            return "managed"


def install_rd_startup_authority_gate(app: Any, manager: Any) -> RdStartupAuthorityGate:
    existing = getattr(app, "rd_startup_authority_gate", None)
    if isinstance(existing, RdStartupAuthorityGate):
        return existing
    gate = RdStartupAuthorityGate(app, manager)
    app.rd_startup_authority_gate = gate
    return gate
