"""Runtime selection policy for the single production charge host."""

from __future__ import annotations

from typing import Any

from cooling_runtime import CoolingAwareShadowRecoveryRuntime


def new_production_runtime(host: Any, *, started_at: float) -> CoolingAwareShadowRecoveryRuntime:
    battery_id = host._v2_battery_id or (
        f"session:{host.battery_type}:{host.ah_capacity}:{int(started_at)}"
    )
    runtime = CoolingAwareShadowRecoveryRuntime(
        battery_id=battery_id,
        started_at=started_at,
        intent=host._v2_intent,
        condition_before=host._v2_condition_before,
    )
    host._v2_runtime = runtime
    return runtime


__all__ = ["new_production_runtime"]
