"""History-based plateau evidence, separate from normal tail completion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..measurements import Measurements


@dataclass(frozen=True)
class PlateauDetectorConfig:
    minimum_samples: int
    voltage_span: float
    minimum_current: float
    max_current_drop: float

    def __post_init__(self) -> None:
        if self.minimum_samples < 1 or min(self.voltage_span, self.minimum_current, self.max_current_drop) < 0:
            raise ValueError("plateau detector configuration is invalid")


class PlateauDetector:
    def __init__(self, config: PlateauDetectorConfig) -> None:
        self.config = config

    def is_plateau(self, history: Sequence[Measurements], *, chemistry: str, is_cv: bool = True) -> bool:
        if not is_cv or len(history) < self.config.minimum_samples:
            return False
        valid = [sample for sample in history if sample.voltage is not None and sample.current is not None]
        if len(valid) < self.config.minimum_samples:
            return False
        voltages = [sample.voltage for sample in valid]
        currents = [sample.current for sample in valid]
        if max(voltages) - min(voltages) > self.config.voltage_span:
            return False
        if min(currents) < self.config.minimum_current:
            return False
        return currents[0] - currents[-1] <= self.config.max_current_drop
