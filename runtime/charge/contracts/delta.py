"""Pure Delta behavior contract data; no Delta program implementation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from ..intent import ChargeIntent


class DeltaState(str, Enum):
    UNARMED = "unarmed"
    TRACKING = "tracking"
    CONFIRMED_HOLD = "confirmed_hold"
    COMPLETE = "complete"
    STOPPED = "stopped"


@dataclass(frozen=True)
class DeltaDecisionCase:
    case_id: str
    current_state: DeltaState
    condition: str
    next_state: DeltaState
    expected_intent: ChargeIntent


DELTA_TRANSITIONS: Tuple[tuple[DeltaState, str, DeltaState, str], ...] = (
    (DeltaState.UNARMED, "fresh valid source and Delta tracking requested", DeltaState.TRACKING, "DELTA_ENTER"),
    (DeltaState.TRACKING, "accepted CV Imin→ΔI or CC Vmax→ΔV confirmation", DeltaState.CONFIRMED_HOLD, "DELTA_HOLD_START"),
    (DeltaState.TRACKING, "evidence not confirmed", DeltaState.TRACKING, "DELTA_HOLD_WAIT"),
    (DeltaState.CONFIRMED_HOLD, "sticky finish hold elapsed", DeltaState.COMPLETE, "DELTA_COMPLETE"),
    (DeltaState.CONFIRMED_HOLD, "hard safety/stop condition", DeltaState.STOPPED, "DELTA_STOP"),
    (DeltaState.TRACKING, "invalid or stale evidence", DeltaState.STOPPED, "DELTA_EVIDENCE_INVALID"),
)


delta_cases = (
    DeltaDecisionCase(
        "delta-enter",
        DeltaState.UNARMED,
        "fresh valid source and Delta tracking requested",
        DeltaState.TRACKING,
        ChargeIntent(14.4, 2.0, "delta", False, "DELTA_ENTER"),
    ),
    DeltaDecisionCase(
        "delta-confirmed-hold",
        DeltaState.TRACKING,
        "accepted CV Imin→ΔI or CC Vmax→ΔV confirmation",
        DeltaState.CONFIRMED_HOLD,
        ChargeIntent(14.4, 2.0, "delta", False, "DELTA_HOLD_START"),
    ),
    DeltaDecisionCase(
        "delta-complete",
        DeltaState.CONFIRMED_HOLD,
        "sticky finish hold elapsed",
        DeltaState.COMPLETE,
        ChargeIntent(14.4, 2.0, "done", True, "DELTA_COMPLETE"),
    ),
    DeltaDecisionCase(
        "delta-invalid-stop",
        DeltaState.TRACKING,
        "invalid or stale evidence",
        DeltaState.STOPPED,
        ChargeIntent(None, None, "stopped", True, "DELTA_EVIDENCE_INVALID"),
    ),
)
