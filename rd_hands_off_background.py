from __future__ import annotations

import time
from typing import Any

from rd_adopted_hands_off_release import install_adopted_hands_off_release_retirement


_SUPPRESSED_NOTIFY_FRAGMENTS = (
    "Сработала защита OVP",
    "Сработала защита OCP",
    "Температура блока",
    "Выключено по условию",
    "Связь потеряна во время активного заряда",
    "Заряд завершён или аккумулятор почти полон",
    "Выход включен, но потребление отсутствует",
)

_SUPPRESSED_EVENT_PREFIXES = (
    "OVP_TRIGGERED",
    "OCP_TRIGGERED",
    "TEMP_INT_PRECRITICAL_",
    "MANUAL_OFF_",
    "WATCHDOG_",
    "SOFT_WATCHDOG_",
    "EMERGENCY_UNAVAILABLE",
    "EMERGENCY_TEMP_",
    "LINK_LOST_DURING_CHARGE",
)


def _external_authority(manager: Any) -> bool:
    return bool(
        manager is not None
        and (
            getattr(manager, "hands_off", False)
            or getattr(manager, "edge_autonomous", False)
        )
    )


def _startup_background_suspended(app: Any) -> bool:
    startup = getattr(app, "rd_startup_authority_gate", None)
    if startup is None or not bool(getattr(startup, "reconciliation_started", False)):
        return False
    if bool(getattr(startup, "recovery_scope", False)):
        return False
    return not bool(getattr(startup, "managed_actuation_ready", False))


def _pb_background_suspended(app: Any, manager: Any) -> bool:
    return _external_authority(manager) or _startup_background_suspended(app)


def _event_name(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if "event" in kwargs:
        return str(kwargs.get("event") or "")
    if len(args) >= 6:
        return str(args[5] or "")
    return ""


def install_hands_off_background_isolation(app: Any, manager: Any) -> None:
    """Make legacy Pb background workers observational outside managed authority."""
    if bool(getattr(app, "_hands_off_background_isolation_installed", False)):
        return

    # Production reaches this after D061 and D065 are installed. Keep isolated unit
    # compositions that intentionally omit D061 usable; bot.py install-order coverage
    # proves the real runtime does compose this retirement boundary.
    if getattr(app, "rd_managed_live_adoption", None) is not None:
        install_adopted_hands_off_release_retirement(app, manager)

    controller = getattr(app, "charge_controller", None)
    if controller is None:
        raise RuntimeError("RD external background isolation requires charge controller")

    original_tick = controller.tick
    original_restore = controller.try_restore_session
    original_hard_stop = getattr(app, "_hard_stop_charge", None)
    original_manual_off_active = getattr(app, "_has_manual_off_condition", None)
    original_operator_pause_active = getattr(app, "_operator_pause_active", None)
    original_notify = getattr(app, "_charge_notify", None)
    original_log_event = getattr(app, "log_event", None)

    async def authority_aware_tick(*args: Any, **kwargs: Any) -> Any:
        if _pb_background_suspended(app, manager):
            controller.last_update_time = time.time()
            return {}
        return await original_tick(*args, **kwargs)

    def authority_aware_restore(*args: Any, **kwargs: Any) -> Any:
        if _pb_background_suspended(app, manager):
            return False, None
        return original_restore(*args, **kwargs)

    async def authority_aware_hard_stop(*args: Any, **kwargs: Any) -> Any:
        if _pb_background_suspended(app, manager):
            return None
        if not callable(original_hard_stop):
            raise RuntimeError("legacy hard-stop helper is unavailable")
        return await original_hard_stop(*args, **kwargs)

    def authority_aware_manual_off(*args: Any, **kwargs: Any) -> bool:
        if _pb_background_suspended(app, manager):
            if _external_authority(manager) and callable(original_manual_off_active) and bool(
                original_manual_off_active(*args, **kwargs)
            ):
                clear = getattr(app, "_clear_manual_off", None)
                if callable(clear):
                    clear()
            return False
        if not callable(original_manual_off_active):
            return False
        return bool(original_manual_off_active(*args, **kwargs))

    def authority_aware_operator_pause(*args: Any, **kwargs: Any) -> bool:
        if _pb_background_suspended(app, manager):
            if _external_authority(manager) and callable(original_operator_pause_active) and bool(
                original_operator_pause_active(*args, **kwargs)
            ):
                clear = getattr(app, "_clear_operator_pause", None)
                if callable(clear):
                    clear()
            return False
        if not callable(original_operator_pause_active):
            return False
        return bool(original_operator_pause_active(*args, **kwargs))

    def authority_aware_notify(message: str, *args: Any, **kwargs: Any) -> Any:
        if _pb_background_suspended(app, manager) and any(
            fragment in str(message or "") for fragment in _SUPPRESSED_NOTIFY_FRAGMENTS
        ):
            return None
        if callable(original_notify):
            return original_notify(message, *args, **kwargs)
        return None

    def authority_aware_log_event(*args: Any, **kwargs: Any) -> Any:
        event = _event_name(args, kwargs)
        if _pb_background_suspended(app, manager) and event.startswith(
            _SUPPRESSED_EVENT_PREFIXES
        ):
            return None
        if callable(original_log_event):
            return original_log_event(*args, **kwargs)
        return None

    controller.tick = authority_aware_tick
    controller.try_restore_session = authority_aware_restore
    if callable(original_hard_stop):
        app._hard_stop_charge = authority_aware_hard_stop
    if callable(original_manual_off_active):
        app._has_manual_off_condition = authority_aware_manual_off
    if callable(original_operator_pause_active):
        app._operator_pause_active = authority_aware_operator_pause
    if callable(original_notify):
        app._charge_notify = authority_aware_notify
        if getattr(controller, "notify", None) is original_notify:
            controller.notify = authority_aware_notify
    if callable(original_log_event):
        app.log_event = authority_aware_log_event

    app._hands_off_background_isolation_installed = True
