"""Pure domain outputs; adapters execute nothing here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
