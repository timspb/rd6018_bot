"""Pure, non-actuating adaptive plateau evidence for EFB recovery recipes.

Shadow-only until canonical MAIN owner integrates the decision. This module
does NOT authorize HV, MIX, recovery stages or physical write operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from statistics import median
from typing import Sequence


class PlateauVerdict(str, Enum):
    OBSERVING = "observing"
    CONFIRMED = "confirmed"
    PROGRESSING = "progressing"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"


@dataclass(frozen=True)
class PlateauRecipe:
    min_window_minutes: float = 90.0
    max_window_minutes: float = 120.0
    end_segment_minutes: float = 15.0
    strong_plateau_drop_a: float = 0.01
    weak_plateau_drop_a: float = 0.02
    near_target_margin_v: float = 0.20

    def __post_init__(self) -> None:
        if not (0 < self.end_segment_minutes < self.min_window_minutes <= self.max_window_minutes):
            raise ValueError("invalid observation window")
        if not (0 <= self.strong_plateau_drop_a <= self.weak_plateau_drop_a):
            raise ValueError("invalid current-change bounds")
        if self.near_target_margin_v < 0:
            raise ValueError("invalid target margin")


@dataclass(frozen=True)
class PlateauSample:
    time_s: float
    current_a: float
    voltage_v: float
    cv: bool
    temp_ok: bool


@dataclass(frozen=True)
class PlateauResult:
    verdict: PlateauVerdict
    elapsed_minutes: float
    current_drop_a: float | None
    reason: str


def observe_recovery_plateau(
    samples: Sequence[PlateauSample],
    *,
    target_voltage_v: float,
    recipe: PlateauRecipe = PlateauRecipe(),
) -> PlateauResult:
    """Evaluate one continuous CV segment; never infer safety from absent data.

    Callers must supply a contiguous observation period and fresh temperature
    verdicts; no decision from this pure function enables physical commands.
    """
    if not samples or not isfinite(target_voltage_v):
        return PlateauResult(PlateauVerdict.INVALID, 0, None, "missing samples or target")
    ordered = sorted(samples, key=lambda x: x.time_s)
    elapsed = (ordered[-1].time_s - ordered[0].time_s) / 60.0
    if (
        len(ordered) < 2
        or elapsed < 0
        or any(not all(isfinite(v) for v in (s.time_s, s.current_a, s.voltage_v)) for s in ordered)
        or any(s.current_a < 0 or not s.cv or not s.temp_ok or
               s.voltage_v < target_voltage_v - recipe.near_target_margin_v for s in ordered)
    ):
        return PlateauResult(PlateauVerdict.INVALID, max(0.0, elapsed), None, "CV, temperature or data invalid")
    if any(b.time_s <= a.time_s or b.time_s-a.time_s > 600 for a, b in zip(ordered, ordered[1:])):
        return PlateauResult(PlateauVerdict.INVALID, elapsed, None, "sample gap exceeds 10 minutes")
    span = recipe.end_segment_minutes * 60
    head = [s.current_a for s in ordered if s.time_s <= ordered[0].time_s + span]
    tail = [s.current_a for s in ordered if s.time_s >= ordered[-1].time_s - span]
    if len(head) < 2 or len(tail) < 2:
        return PlateauResult(PlateauVerdict.INVALID, elapsed, None, "insufficient segment samples")
    drop = median(head) - median(tail)
    if elapsed < recipe.min_window_minutes:
        return PlateauResult(PlateauVerdict.OBSERVING, elapsed, drop, "minimum window not reached")
    if drop < -recipe.strong_plateau_drop_a:
        return PlateauResult(PlateauVerdict.INCONCLUSIVE, elapsed, drop, "current rise; no automatic escalation")
    if drop <= recipe.strong_plateau_drop_a:
        return PlateauResult(PlateauVerdict.CONFIRMED, elapsed, drop, "stable plateau after 90+ minutes")
    if drop > recipe.weak_plateau_drop_a:
        return PlateauResult(PlateauVerdict.PROGRESSING, elapsed, drop, "meaningful current decline")
    if elapsed < recipe.max_window_minutes:
        return PlateauResult(PlateauVerdict.OBSERVING, elapsed, drop, "ambiguous decline; extend toward 120 minutes")
    return PlateauResult(PlateauVerdict.INCONCLUSIVE, elapsed, drop, "ambiguous at 120 minutes; no automatic escalation")
