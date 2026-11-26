"""Single owner for the data logger's existing link-outage state transition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OutageCategory = Literal["initial_read", "cycle_readback", "unexpected_cycle"]


@dataclass(frozen=True)
class LinkOutageTransition:
    """Effects for the runtime adapter; counters remain owned by its app state."""

    failure_streak: int
    alert_sent: bool
    mark_unavailable: bool
    notify_repeated_outage: bool = False
    notify_active_charge_loss: bool = False
    stop_idle_session: bool = False
    request_emergency_off: bool = False


def transition_link_outage(
    *,
    category: OutageCategory,
    recoverable_link_error: bool,
    failure_streak: int,
    alert_sent: bool,
    last_known_output_on: bool,
    session_active: bool,
    notification_threshold: int,
) -> LinkOutageTransition:
    """Resolve one existing outage branch without owning storage or side effects.

    Transport classification stays in ``runtime.physical.transports``. Only
    established unexpected cycle failures can request verified emergency OFF.
    """
    if category not in {"initial_read", "cycle_readback", "unexpected_cycle"}:
        raise ValueError(f"unsupported link outage category: {category}")

    if recoverable_link_error:
        next_streak = failure_streak + 1
        should_notify = (
            last_known_output_on
            and next_streak >= notification_threshold
            and not alert_sent
        )
        return LinkOutageTransition(
            failure_streak=next_streak,
            alert_sent=alert_sent or should_notify,
            mark_unavailable=True,
            notify_repeated_outage=should_notify,
        )

    if category == "unexpected_cycle":
        should_notify = last_known_output_on and not alert_sent
        return LinkOutageTransition(
            failure_streak=failure_streak,
            alert_sent=alert_sent or should_notify,
            mark_unavailable=True,
            notify_active_charge_loss=should_notify,
            stop_idle_session=not last_known_output_on and session_active,
            request_emergency_off=last_known_output_on,
        )

    return LinkOutageTransition(
        failure_streak=failure_streak,
        alert_sent=alert_sent,
        mark_unavailable=False,
    )
