"""Pure charge-domain outputs; adapters execute nothing here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AuthorityAction(str, Enum):
    """Canonical charge-stage transition actions."""

    CONTINUE = "continue"
    ADVANCE_AGM_STEP = "advance_agm_step"
    ENTER_DESULFATION = "enter_desulfation"
    ENTER_MIX = "enter_mix"
    START_FINISH_HOLD = "start_finish_hold"
    COMPLETE_TO_SAFE_WAIT = "complete_to_safe_wait"
    STOP_AND_DIAGNOSE = "stop_and_diagnose"


@dataclass(frozen=True)
class AuthorityDecision:
    """Pure strategy decision; execution is applied by a separate owner."""

    action: AuthorityAction
    reason: str


@dataclass(frozen=True)
class ActuatorIntent:
    """Domain request for a future execution boundary, not a physical call."""

    operation: str
    voltage: Optional[float] = None
    current: Optional[float] = None
    reason: str = ""


@dataclass(frozen=True)
class ContainmentResultRequest:
    """Domain request to enter containment; no owner is invoked here."""

    trigger: str
    reason: str


@dataclass(frozen=True)
class DomainDecision:
    """Pure output of one domain evaluation."""

    stage: Optional[str]
    intent: Optional[ActuatorIntent]
    containment: Optional[ContainmentResultRequest] = None
    completed: bool = False
    reason: str = ""


__all__ = [
    "ActuatorIntent",
    "AuthorityAction",
    "AuthorityDecision",
    "ContainmentResultRequest",
    "DomainDecision",
]
