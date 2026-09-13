"""Pure data model for charge state; no runtime integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass
class ChargeState:
    """Current charge data supplied to a program.

    This model contains no behavior and never performs physical or transport
    operations.  ``measurements`` is a read-only-by-convention snapshot owned by
    the caller; program implementations must not mutate it.
    """

    program: Optional[str] = None
    mode: Optional[str] = None
    stage: Optional[str] = None
    timers: Dict[str, float] = field(default_factory=dict)
    targets: Dict[str, Optional[float]] = field(default_factory=dict)
    measurements: Mapping[str, Any] = field(default_factory=dict)
    completed: bool = False

