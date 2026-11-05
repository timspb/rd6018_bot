"""Recipe-owned recovery plateau observation inside the existing MAIN tick.

The observer is diagnostic only: it neither selects a charging stage nor
owns any actuator, safety lease, output or recovery authority.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import isfinite
from typing import Deque

from .recovery_plateau_policy import (
    PlateauRecipe, PlateauResult, PlateauSample, PlateauVerdict,
    observe_recovery_plateau,
)


@dataclass
class RecoveryPlateauObserver:
    recipe: PlateauRecipe = field(default_factory=PlateauRecipe)
    samples: Deque[PlateauSample] = field(default_factory=deque)
    previous_target_v: float | None = None
    previous_session: str | None = None

    def reset(self) -> None:
        self.samples.clear()
        self.previous_target_v = None
        self.previous_session = None

    def observe(
        self, *,
        session_id: str,
        timestamp_s: float,
        voltage_v: float,
        current_a: float,
        target_voltage_v: float,
        is_cv: bool,
        temp_valid: bool,
        eligible: bool,
    ) -> PlateauResult:
        if not eligible:
            self.reset()
            return PlateauResult(PlateauVerdict.INVALID, 0, None, "non-EFB recovery MAIN")
        values = (timestamp_s, voltage_v, current_a, target_voltage_v)
        if (not session_id or any(not isfinite(v) for v in values)
                or current_a < 0 or not is_cv or not temp_valid
                or voltage_v < target_voltage_v - self.recipe.near_target_margin_v):
            self.reset()
            return PlateauResult(PlateauVerdict.INVALID, 0, None, "non-qualifying CV/telemetry")
        if self.previous_session != session_id or (
            self.previous_target_v is not None
            and abs(self.previous_target_v - target_voltage_v) > 0.02
        ):
            self.reset()
        if self.samples and (
            timestamp_s <= self.samples[-1].time_s
            or timestamp_s - self.samples[-1].time_s > 600
        ):
            self.reset()
        self.previous_session = session_id
        self.previous_target_v = target_voltage_v
        self.samples.append(PlateauSample(
            time_s=timestamp_s,
            current_a=current_a,
            voltage_v=voltage_v,
            cv=is_cv,
            temp_ok=temp_valid,
        ))
        # Keep one rolling, bounded 120-minute window; do not backdate
        # from the old 15-minute analyzer or extend observations across gaps.
        cutoff = timestamp_s - self.recipe.max_window_minutes * 60
        while len(self.samples) > 2 and self.samples[1].time_s < cutoff:
            self.samples.popleft()
        return observe_recovery_plateau(
            tuple(self.samples),
            target_voltage_v=target_voltage_v,
            recipe=self.recipe,
        )
