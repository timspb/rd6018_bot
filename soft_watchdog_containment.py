from __future__ import annotations

import asyncio
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
    """Return True when Pb software no longer owns RD actuator authority.

    HANDS_OFF is an outer ownership boundary, not a degraded managed-charge state.
    The legacy HA heartbeat watchdog must therefore remain completely non-actuating
    while HANDS_OFF owns the PSU, including during the live release transaction.
    """
    manager = getattr(app, "rd_control_mode_manager", None)
    if manager is None:
        return False
    return bool(
        getattr(manager, "hands_off", False)
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

    # The runtime guard is the final production view of controller ownership.  It
    # includes first-class Manual authority and may grow additional managed authority
    # without forcing the legacy watchdog to learn chemistry/session details.
    guard = getattr(app, "runtime_safety_guard", None)
    if guard is not None:
        try:
            if bool(getattr(guard, "controller_active")):
                return True
        except Exception:
            # Ownership ambiguity must not be interpreted as proof that no managed
            # command exists. Fall back to the positive evidence above; the local edge
            # lease remains the independent blind-operation bound.
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
    """Run one legacy soft-watchdog decision without creating an actuator storm.

    The data/logger heartbeat remains the authority for detecting the outage while Pb
    software owns RD. An idle PB-managed system whose last known Output is OFF is
    passive. If Output was known ON or a managed command is still active, request the
    existing hard-stop path immediately and retry failed remote shutdowns only at a
    bounded cadence.

    HANDS_OFF is outside this watchdog's authority entirely. Entering HANDS_OFF resets
    any in-process Pb outage incident and no hard-stop/protection write is attempted,
    even if legacy state still remembers that Output was ON before the ownership
    transfer. Intrinsic RD protections remain local hardware behavior.
    """
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
        # Output was last known OFF and no managed command survives. This is the
        # operator contract for idle telemetry loss: quiet/passive containment.
        return

    if not incident.logged:
        incident.logged = True
        logger = getattr(app, "logger", None)
        if logger is not None:
            logger.critical(
                "CRITICAL: Soft Watchdog timeout while managed/energized; requesting bounded Output OFF containment."
            )
        _log_watchdog_incident(app)

    if incident.shutdown_complete:
        return

    if (
        incident.last_attempt_at > 0.0
        and current - incident.last_attempt_at < SOFT_WATCHDOG_RETRY_S
    ):
        return

    # Latch the retry timestamp before issuing I/O so exceptions cannot turn the
    # 10-second outer poll into a command storm.
    incident.last_attempt_at = current
    try:
        await app._hard_stop_charge()
    except Exception as exc:
        logger = getattr(app, "logger", None)
        if logger is not None:
            logger.error("soft watchdog shutdown attempt failed: %s", exc)
        return

    # _hard_stop_charge returns only after its Output-OFF transaction and protection
    # reset completed. Do not issue more actuator commands for the same outage.
    incident.shutdown_complete = True


def install_soft_watchdog_containment(app: Any) -> SoftWatchdogIncident:
    if bool(getattr(app, "_soft_watchdog_containment_installed", False)):
        return app._soft_watchdog_incident

    incident = SoftWatchdogIncident()

    async def bounded_soft_watchdog_loop() -> None:
        while True:
            await asyncio.sleep(10)
            try:
                await soft_watchdog_poll_once(app, incident)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger = getattr(app, "logger", None)
                if logger is not None:
                    logger.error("soft_watchdog_loop: %s", exc)

    app.soft_watchdog_loop = bounded_soft_watchdog_loop
    app._soft_watchdog_incident = incident
    app._soft_watchdog_containment_installed = True
    return incident
