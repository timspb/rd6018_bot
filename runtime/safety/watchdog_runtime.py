"""Single production software-safety observer; all policies remain module-owned."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from runtime.safety.communication_watchdog import communication_shutdown_due
from runtime.safety.communication_variables import (
    SOFT_WATCHDOG_POLL_S, COMMUNICATION_WATCHDOG_POLL_S,
)
from runtime.safety.soft_watchdog import SoftWatchdogIncident, soft_watchdog_poll_once

SOFT_POLL_S = float(SOFT_WATCHDOG_POLL_S.default)
COMM_POLL_S = float(COMMUNICATION_WATCHDOG_POLL_S.default)


async def communication_watchdog_poll_once(app: Any, *, now_epoch_s: float | None = None,
                                          now_monotonic_s: float | None = None) -> bool:
    """Apply existing communication containment once; return whether OFF requested."""
    last = getattr(app.charge_controller, "last_update_time", 0.0)
    if not isinstance(last, (int, float)) or last <= 0:
        return False
    live = await app.hass.get_all_live()
    guard = getattr(app, "runtime_safety_guard", None)
    timeout = float(app.WATCHDOG_TIMEOUT)
    if not communication_shutdown_due(
        live,
        now_epoch_s=time.time() if now_epoch_s is None else now_epoch_s,
        last_controller_update_epoch_s=float(last),
        now_monotonic_s=time.monotonic() if now_monotonic_s is None else now_monotonic_s,
        guard_recovery_active=bool(getattr(guard, "telemetry_recovery_active", False)),
        timeout_s=timeout,
    ):
        return False
    app.logger.critical("CRITICAL: Watchdog timeout. Emergency shutdown.")
    from rd6018_telemetry import finite_float
    def number(name: str) -> float:
        value = finite_float(live.get(name))
        return value if value is not None else 0.0
    app.log_event(app.charge_controller.current_stage,
                  number("voltage"), number("current"), number("temp_ext"),
                  number("ah"), "WATCHDOG_TIMEOUT")
    await app._hard_stop_charge()
    return True


async def run_safety_watchdogs(app: Any) -> None:
    """One lifecycle task, preserving soft 10s and communication 30s cadence.

    Individual observers remain isolated on error. All physical OFF requests
    still pass through the established runtime execution owner.
    """
    incident = SoftWatchdogIncident()
    next_communication = time.monotonic() + COMM_POLL_S
    while True:
        await asyncio.sleep(SOFT_POLL_S)
        try:
            await soft_watchdog_poll_once(app, incident)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app.logger.error("soft_watchdog_loop: %s", exc)
        now = time.monotonic()
        if now < next_communication:
            continue
        next_communication = now + COMM_POLL_S
        # A latched soft-watchdog incident already owns repeated verified OFF.
        # Never let a second policy send a competing OFF for that incident.
        if incident.active and incident.logged:
            continue
        try:
            await communication_watchdog_poll_once(app)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app.logger.error("watchdog_loop: %s", exc)
