"""Pure result model for a charge program evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChargeIntent:
    """A requested charge transition, not a physical command."""

    target_voltage: Optional[float] = None
    target_current: Optional[float] = None
    next_stage: Optional[str] = None
    completed: bool = False
    reason: str = ""

