from __future__ import annotations

import time
from typing import Any


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


def _hands_off(manager: Any) -> bool:
    return bool(manager is not None and getattr(manager, "hands_off", False))


def _event_name(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if "event" in kwargs:
        return str(kwargs.get("event") or "")
    if len(args) >= 6:
        return str(args[5] or "")
    return ""


def install_hands_off_background_isolation(app: Any, manager: Any) -> None:
    """Keep legacy background workers observational while RD is in HANDS_OFF.

    `rd_control_mode` already blocks final actuator writes, but the old data logger,
    watchdog and charge monitor still execute Pb-era control logic around those writes.
    In HANDS_OFF that created repeated exceptions, misleading "Output выключен" alerts,
    stale restore attempts and persistent Manual-Off/operator-pause authority even
    though D060 says Pb software no longer owns the external PSU.

    This compatibility layer is deliberately narrow: it changes behavior only after
    durable HANDS_OFF is active. During PB_MANAGED and the pre-commit live-release
    window every existing safety path remains unchanged, including verified OFF.
    """
    if bool(getattr(app, "_hands_off_background_isolation_installed", False)):
        return

    controller = getattr(app, "charge_controller", None)
    if controller is None:
        raise RuntimeError("RD HANDS_OFF background isolation requires charge controller")

    original_tick = controller.tick
    original_restore = controller.try_restore_session
    original_hard_stop = getattr(app, "_hard_stop_charge", None)
    original_manual_off_active = getattr(app, "_has_manual_off_condition", None)
    original_operator_pause_active = getattr(app, "_operator_pause_active", None)
    original_notify = getattr(app, "_charge_notify", None)
    original_log_event = getattr(app, "log_event", None)

    async def hands_off_aware_tick(*args: Any, **kwargs: Any) -> Any:
        if _hands_off(manager):
            # Keep the legacy watchdog heartbeat fresh without running chemistry or
            # emitting actuator actions. The data logger still stores raw telemetry.
            controller.last_update_time = time.time()
            return {}
        return await original_tick(*args, **kwargs)

    def hands_off_aware_restore(*args: Any, **kwargs: Any) -> Any:
        if _hands_off(manager):
            # Background restore probing is not an operator authorization. Returning
            # the ordinary "no session restored" result avoids turning HANDS_OFF into
            # an exception/link-loss loop while preserving explicit start guards.
            return False, None
        return original_restore(*args, **kwargs)

    async def hands_off_aware_hard_stop(*args: Any, **kwargs: Any) -> Any:
        if _hands_off(manager):
            # Intrinsic RD protections remain hardware authority. Pb software must not
            # issue a compensating OFF or protection rewrite in general-purpose mode.
            return None
        if not callable(original_hard_stop):
            raise RuntimeError("legacy hard-stop helper is unavailable")
        return await original_hard_stop(*args, **kwargs)

    def hands_off_aware_manual_off_active(*args: Any, **kwargs: Any) -> bool:
        if _hands_off(manager):
            if callable(original_manual_off_active) and bool(
                original_manual_off_active(*args, **kwargs)
            ):
                clear = getattr(app, "_clear_manual_off", None)
                if callable(clear):
                    clear()
            return False
        if not callable(original_manual_off_active):
            return False
        return bool(original_manual_off_active(*args, **kwargs))

    def hands_off_aware_operator_pause(*args: Any, **kwargs: Any) -> bool:
        if _hands_off(manager):
            if callable(original_operator_pause_active) and bool(
                original_operator_pause_active(*args, **kwargs)
            ):
                clear = getattr(app, "_clear_operator_pause", None)
                if callable(clear):
                    clear()
            return False
        if not callable(original_operator_pause_active):
            return False
        return bool(original_operator_pause_active(*args, **kwargs))

    def hands_off_aware_notify(message: str, *args: Any, **kwargs: Any) -> Any:
        if _hands_off(manager) and any(
            fragment in str(message or "") for fragment in _SUPPRESSED_NOTIFY_FRAGMENTS
        ):
            return None
        if callable(original_notify):
            return original_notify(message, *args, **kwargs)
        return None

    def hands_off_aware_log_event(*args: Any, **kwargs: Any) -> Any:
        event = _event_name(args, kwargs)
        if _hands_off(manager) and event.startswith(_SUPPRESSED_EVENT_PREFIXES):
            return None
        if callable(original_log_event):
            return original_log_event(*args, **kwargs)
        return None

    controller.tick = hands_off_aware_tick
    controller.try_restore_session = hands_off_aware_restore
    if callable(original_hard_stop):
        app._hard_stop_charge = hands_off_aware_hard_stop
    if callable(original_manual_off_active):
        app._has_manual_off_condition = hands_off_aware_manual_off_active
    if callable(original_operator_pause_active):
        app._operator_pause_active = hands_off_aware_operator_pause
    if callable(original_notify):
        app._charge_notify = hands_off_aware_notify
        # Controller.notify was captured during construction and bypasses later module
        # global replacement. Point it at the same ownership-aware notification gate.
        if getattr(controller, "notify", None) is original_notify:
            controller.notify = hands_off_aware_notify
    if callable(original_log_event):
        app.log_event = hands_off_aware_log_event

    app._hands_off_background_isolation_installed = True
