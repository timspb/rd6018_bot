"""Post-charge boundary marker; orchestration is intentionally external."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FinishIntent:
    next_layer: str
    reason: str
    target_voltage: Optional[float] = None
    target_current: Optional[float] = None
