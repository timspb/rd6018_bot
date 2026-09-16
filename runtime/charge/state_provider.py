"""Read-only construction boundary for V3 ChargeState snapshots."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .battery import BatteryProfile
from .state import ChargeState


class ChargeStateProvider:
    """Build a data snapshot from supplied runtime observations.

    The provider has no internal mutable state.  It does not read integrations,
    mutate a controller, or apply any returned state to a physical device.
    """

    def build(
        self,
        *,
        active_program: Optional[str],
        mode: Optional[str],
        stage: Optional[str],
        targets: Mapping[str, Optional[float]],
        timers: Mapping[str, float],
        completed: bool,
        measurements: Mapping[str, Any],
        battery_profile: Optional[BatteryProfile] = None,
    ) -> ChargeState:
        """Return a new snapshot; input mappings are copied as snapshot data."""
        state = ChargeState(
            program=active_program,
            mode=mode,
            stage=stage,
            targets=dict(targets),
            timers=dict(timers),
            measurements=measurements,
            completed=bool(completed),
        )
        # Battery identity is tracked by the service/domain case currently;
        # ChargeState remains backwards-compatible and data-only in Phase 7.
        _ = battery_profile
        return state
