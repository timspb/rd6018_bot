"""Canonical bounded software-watchdog containment for managed RD6018 authority."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


SOFT_WATCHDOG_RETRY_S = 60.0


@dataclass
class SoftWatchdogIncident:
    active: bool = False
    logged: bool = False
    shutdown_complete: bool = False
    last_attempt_at: float = 0.0

    def reset(self) -> None:
        self.active = False
        self.logged = False
        self.shutdown_complete = False
        self.last_attempt_at = 0.0


def _pb_watchdog_suspended(app: Any) -> bool:
    """Return True when Pb software does not have reconciled actuator authority."""

    manager = getattr(app, "rd_control_mode_manager", None)
    if manager is None:
        return False
    startup = getattr(app, "rd_startup_authority_gate", None)
    if startup is not None and not bool(
        getattr(startup, "managed_actuation_ready", False)
    ):
        return True
    return bool(
        getattr(manager, "hands_off", False)
        or getattr(manager, "edge_autonomous", False)
        or getattr(manager, "release_in_progress", False)
    )


def _managed_authority_active(app: Any) -> bool:
    if _pb_watchdog_suspended(app):
        return False

    controller = getattr(app, "charge_controller", None)
    if controller is not None:
        if bool(getattr(controller, "_last_known_output_on", False)):
            return True
        if bool(getattr(controller, "is_active", False)):
            return True

    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and bool(getattr(manual, "is_active", False)):
        return True

    guard = getattr(app, "runtime_safety_guard", None)
    if guard is not None:
        try:
            if bool(getattr(guard, "controller_active")):
                return True
        except Exception:
            pass
    return False


def _log_watchdog_incident(app: Any) -> None:
    controller = getattr(app, "charge_controller", None)
    stage = getattr(controller, "current_stage", "unknown")
    try:
        app.log_event(
            stage,
            0.0,
            0.0,
            0.0,
            0.0,
            "SOFT_WATCHDOG_HA_LOST",
        )
    except Exception:
        pass


async def soft_watchdog_poll_once(
    app: Any,
    incident: SoftWatchdogIncident,
    *,
    now: Optional[float] = None,
) -> None:
    """Apply bounded software-watchdog containment for one observation cycle."""

    current = time.time() if now is None else float(now)
    last_ok = float(getattr(app, "last_ha_ok_time", 0.0) or 0.0)
    timeout = float(getattr(app, "SOFT_WATCHDOG_TIMEOUT", 180.0))

    if last_ok <= 0.0 or current - last_ok < timeout:
        incident.reset()
        return

    if _pb_watchdog_suspended(app):
        incident.reset()
        return

    incident.active = True
    if not _managed_authority_active(app):
        return

    if not incident.logged:
        incident.logged = True
        logger = getattr(app, "logger", None)
        if logger is not None:
            logger.critical(
                "CRITICAL: Soft Watchdog timeout while managed/energized; "
                "requesting bounded Output OFF containment."
            )
        _log_watchdog_incident(app)

    if incident.shutdown_complete:
        return

    if (
        incident.last_attempt_at > 0.0
        and current - incident.last_attempt_at < SOFT_WATCHDOG_RETRY_S
    ):
        return

    incident.last_attempt_at = current
    try:
        await app._hard_stop_charge()
    except Exception as exc:
        logger = getattr(app, "logger", None)
        if logger is not None:
            logger.error("soft watchdog shutdown attempt failed: %s", exc)
        return

    incident.shutdown_complete = True


__all__ = [
    "SOFT_WATCHDOG_RETRY_S",
    "SoftWatchdogIncident",
    "soft_watchdog_poll_once",
]
