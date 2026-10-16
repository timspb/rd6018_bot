"""Pure decision policy for the managed software watchdog."""

from __future__ import annotations

import math
from dataclasses import dataclass


SOFT_WATCHDOG_RETRY_S = 60.0


@dataclass(frozen=True)
class WatchdogSnapshot:
    """Normalized values observed by the effect-owning watchdog adapter."""

    now: float
    last_heartbeat_at: float
    timeout_s: float
    authority_suspended: bool
    managed_authority_active: bool


@dataclass(frozen=True)
class WatchdogIncidentState:
    active: bool = False
    logged: bool = False
    shutdown_complete: bool = False
    last_attempt_at: float = 0.0


@dataclass(frozen=True)
class WatchdogDecision:
    incident: WatchdogIncidentState
    log_incident: bool = False
    attempt_shutdown: bool = False


def decide_watchdog(
    snapshot: WatchdogSnapshot,
    incident: WatchdogIncidentState,
) -> WatchdogDecision:
    """Return the next incident state and requested effects without performing them."""

    now = snapshot.now
    heartbeat = snapshot.last_heartbeat_at
    timeout = snapshot.timeout_s
    # Preserve the former adapter's comparisons exactly. In particular, NaN
    # comparisons are false, so malformed clock/timeout evidence does not
    # suppress containment; zero/nonpositive timeouts also retain their old
    # aged-heartbeat behavior. A missing heartbeat (<= 0) remains a reset.
    if heartbeat <= 0.0 or (now - heartbeat) < timeout or snapshot.authority_suspended:
        return WatchdogDecision(WatchdogIncidentState())

    active = WatchdogIncidentState(
        active=True,
        logged=incident.logged,
        shutdown_complete=incident.shutdown_complete,
        last_attempt_at=incident.last_attempt_at,
    )
    if not snapshot.managed_authority_active:
        return WatchdogDecision(active)

    should_log = not incident.logged
    active = WatchdogIncidentState(
        active=True,
        logged=True,
        shutdown_complete=incident.shutdown_complete,
        last_attempt_at=incident.last_attempt_at,
    )
    if incident.shutdown_complete:
        return WatchdogDecision(active, log_incident=should_log)

    last_attempt = incident.last_attempt_at
    if not math.isfinite(last_attempt):
        last_attempt = 0.0
    if last_attempt > 0.0 and now - last_attempt < SOFT_WATCHDOG_RETRY_S:
        return WatchdogDecision(active, log_incident=should_log)

    active = WatchdogIncidentState(
        active=True,
        logged=True,
        shutdown_complete=False,
        last_attempt_at=now,
    )
    return WatchdogDecision(active, log_incident=should_log, attempt_shutdown=True)


__all__ = [
    "SOFT_WATCHDOG_RETRY_S",
    "WatchdogDecision",
    "WatchdogIncidentState",
    "WatchdogSnapshot",
    "decide_watchdog",
]
