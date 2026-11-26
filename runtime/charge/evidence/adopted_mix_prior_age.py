"""Pure D063 prior-Mix age projection and conservative evidence selection."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from runtime.charge.strategy.adopted_mix_admission import _finite_nonnegative
from runtime.safety.runtime_guard import RuntimeSafetyError


class PriorMixAgeSource(str, Enum):
    RECORDER = "recorder"
    OPERATOR_DECLARED = "operator_declared"


@dataclass(frozen=True)
class PriorMixAge:
    elapsed_s: float
    source: PriorMixAgeSource
    observed_at_s: float


def aged_elapsed(elapsed_s: float, observed_at_s: float, now_s: float) -> float:
    """Project an elapsed age forward; wall-clock rollback never reduces it."""
    elapsed = _finite_nonnegative(elapsed_s, field="prior Mix age")
    observed = float(observed_at_s)
    now = float(now_s)
    if not math.isfinite(observed) or not math.isfinite(now):
        raise RuntimeSafetyError("prior Mix age timestamp is invalid")
    return elapsed + max(0.0, now - observed)


def resolve_prior_mix_age(
    history: Optional[Any],
    *,
    declared_elapsed_s: Optional[float] = None,
    declared_at_s: Optional[float] = None,
    now_s: Optional[float] = None,
) -> PriorMixAge:
    """Resolve initial age from reliable Recorder and/or explicit operator evidence."""
    now = float(now_s if now_s is not None else time.time())
    candidates: list[PriorMixAge] = []
    if history is not None and history.output.reliable and history.output.elapsed_s is not None:
        elapsed = aged_elapsed(history.output.elapsed_s, history.fetched_at_s, now)
        candidates.append(PriorMixAge(elapsed, PriorMixAgeSource.RECORDER, now))
    if declared_elapsed_s is not None:
        observed = float(declared_at_s if declared_at_s is not None else now)
        elapsed = aged_elapsed(declared_elapsed_s, observed, now)
        candidates.append(PriorMixAge(elapsed, PriorMixAgeSource.OPERATOR_DECLARED, now))
    if not candidates:
        raise RuntimeSafetyError(
            "prior external Mix age is not proven; declare elapsed active time or remain HANDS_OFF/Manual/OFF"
        )
    # max() is stable: Recorder retains precedence on exact ties, as before.
    return max(candidates, key=lambda item: item.elapsed_s)


def age_prior_mix_age(floor: PriorMixAge, *, now_s: float) -> PriorMixAge:
    now = float(now_s)
    return PriorMixAge(aged_elapsed(floor.elapsed_s, floor.observed_at_s, now), floor.source, now)


def select_fresh_recorder_age(
    aged_floor: PriorMixAge,
    history: Optional[Any],
    *,
    now_s: float,
) -> PriorMixAge:
    """Extend an already-aged floor only with a strictly larger reliable report."""
    now = float(now_s)
    if history is None or not history.output.reliable or history.output.elapsed_s is None:
        return aged_floor
    fresh = PriorMixAge(
        aged_elapsed(history.output.elapsed_s, history.fetched_at_s, now),
        PriorMixAgeSource.RECORDER,
        now,
    )
    return fresh if fresh.elapsed_s > aged_floor.elapsed_s else aged_floor
