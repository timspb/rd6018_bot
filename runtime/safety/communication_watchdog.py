"""Pure communication-watchdog eligibility; no transport or hardware effects."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from runtime.safety.variables import WATCHDOG_TIMEOUT_S


def communication_shutdown_due(
    live: Mapping[str, Any], *,
    now_epoch_s: float,
    last_controller_update_epoch_s: float,
    now_monotonic_s: float,
    guard_recovery_active: bool = False,
    timeout_s: float = float(WATCHDOG_TIMEOUT_S.default),
) -> bool:
    """Return whether established managed Output requires containment.

    Do not create another timeout epoch. Native partial-recovery and managed
    callback grace remain exclusively owned by ManagedRuntimeSafetyGuard.
    """
    if not (
        math.isfinite(now_epoch_s) and math.isfinite(now_monotonic_s)
        and math.isfinite(last_controller_update_epoch_s)
        and last_controller_update_epoch_s > 0
        and math.isfinite(timeout_s) and timeout_s > 0
    ):
        return False
    native_since = live.get("_native_link_outage_since")
    native_recovering = (
        isinstance(native_since, (int, float))
        and not isinstance(native_since, bool)
        and math.isfinite(native_since)
        and 0 <= now_monotonic_s - native_since < timeout_s
    )
    if (native_recovering or guard_recovery_active
            or live.get("_managed_telemetry_recovery_pending") is True):
        return False
    return (
        str(live.get("switch", "")).lower() == "on"
        and now_epoch_s - last_controller_update_epoch_s >= timeout_s
    )
