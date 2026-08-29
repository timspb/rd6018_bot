from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Tuple


class DiagnosticHypothesis(str, Enum):
    CELL_FAULT = "cell_fault"
    SELF_DISCHARGE = "self_discharge"
    SULFATION = "sulfation"
    STRATIFICATION = "stratification"
    CAPACITY_LOSS = "capacity_loss"
    THERMAL_ABNORMALITY = "thermal_abnormality"
    CHARGER_PATH = "charger_path"


class DiagnosticLevel(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    VERIFY = "verify"
    PROBABLE = "probable"
    HIGH = "high"


@dataclass(frozen=True)
class SpecificGravityMeasurement:
    """Manual per-cell flooded-battery evidence.

    Cell positions are kept even when one cell cannot be measured.  Raw SG is stored;
    temperature correction is deliberately not guessed here because hydrometer and
    manufacturer correction conventions differ.  The measurement temperature remains
    attached to the evidence so a chemistry/manufacturer-specific correction can be
    applied later without destroying the original reading.
    """

    battery_id: str
    measured_at: float
    cells: Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]
    temperature_c: Optional[float] = None
    context: str = ""
    notes: str = ""
    source: str = "manual"

    def __post_init__(self) -> None:
        if not self.battery_id.strip():
            raise ValueError("battery_id is required")
        if not math.isfinite(float(self.measured_at)) or self.measured_at <= 0:
            raise ValueError("measured_at must be a positive finite timestamp")
        if len(self.cells) != 6:
            raise ValueError("a 12V lead-acid battery must keep exactly six cell slots")
        for index, value in enumerate(self.cells, start=1):
            if value is None:
                continue
            numeric = float(value)
            if not math.isfinite(numeric) or not (1.0 <= numeric <= 1.4):
                raise ValueError(f"cell {index} SG is implausible: {value!r}")
        if self.temperature_c is not None and not math.isfinite(float(self.temperature_c)):
            raise ValueError("temperature_c must be finite when present")

    @classmethod
    def from_iterable(
        cls,
        *,
        battery_id: str,
        measured_at: float,
        cells: Iterable[Optional[float]],
        temperature_c: Optional[float] = None,
        context: str = "",
        notes: str = "",
        source: str = "manual",
    ) -> "SpecificGravityMeasurement":
        values = tuple(None if value is None else float(value) for value in cells)
        if len(values) != 6:
            raise ValueError("exactly six cell positions are required")
        return cls(
            battery_id=battery_id,
            measured_at=float(measured_at),
            cells=values,  # type: ignore[arg-type]
            temperature_c=temperature_c,
            context=str(context),
            notes=str(notes),
            source=str(source),
        )


@dataclass(frozen=True)
class SpecificGravityAssessment:
    valid_cell_count: int
    minimum: Optional[float]
    maximum: Optional[float]
    median: Optional[float]
    spread: Optional[float]
    low_outlier_cells: Tuple[int, ...]
    high_outlier_cells: Tuple[int, ...]
    level: DiagnosticLevel
    reason: str


SG_SPREAD_VERIFY = 0.030
SG_OUTLIER_DELTA = 0.020


def assess_specific_gravity(
    measurement: SpecificGravityMeasurement,
    *,
    spread_verify: float = SG_SPREAD_VERIFY,
    outlier_delta: float = SG_OUTLIER_DELTA,
) -> SpecificGravityAssessment:
    indexed = [(idx, float(value)) for idx, value in enumerate(measurement.cells, start=1) if value is not None]
    if not indexed:
        return SpecificGravityAssessment(0, None, None, None, None, (), (), DiagnosticLevel.WATCH, "no_cell_measurements")

    values = [value for _, value in indexed]
    minimum = min(values)
    maximum = max(values)
    median = statistics.median(values)
    spread = maximum - minimum
    low = tuple(idx for idx, value in indexed if median - value >= outlier_delta)
    high = tuple(idx for idx, value in indexed if value - median >= outlier_delta)

    # SG imbalance is strong external evidence but not, by itself, proof of a shorted
    # cell.  It escalates diagnostics to VERIFY; actuator blocking needs the separate
    # multi-signal confirmed-fault contract.
    if len(values) < 6:
        level = DiagnosticLevel.WATCH
        reason = "partial_cell_measurement"
    elif spread >= spread_verify:
        level = DiagnosticLevel.VERIFY
        reason = "cell_specific_gravity_imbalance"
    else:
        level = DiagnosticLevel.NORMAL
        reason = "cell_specific_gravity_balanced"

    return SpecificGravityAssessment(
        valid_cell_count=len(values),
        minimum=minimum,
        maximum=maximum,
        median=median,
        spread=spread,
        low_outlier_cells=low,
        high_outlier_cells=high,
        level=level,
        reason=reason,
    )


@dataclass(frozen=True)
class DynamicLoopProbe:
    """Two-wire controlled charge-response evidence, not battery internal resistance."""

    battery_id: str
    measured_at: float
    stage: str
    baseline_voltage_v: float
    baseline_current_a: float
    stepped_voltage_v: float
    stepped_current_a: float
    connection_id: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        values = (
            self.measured_at,
            self.baseline_voltage_v,
            self.baseline_current_a,
            self.stepped_voltage_v,
            self.stepped_current_a,
        )
        if not self.battery_id.strip():
            raise ValueError("battery_id is required")
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("probe values must be finite")
        if self.measured_at <= 0:
            raise ValueError("measured_at must be positive")

    @property
    def delta_current_a(self) -> float:
        return self.stepped_current_a - self.baseline_current_a

    @property
    def delta_voltage_v(self) -> float:
        return self.stepped_voltage_v - self.baseline_voltage_v

    @property
    def dynamic_loop_ohm(self) -> Optional[float]:
        delta_i = self.delta_current_a
        if abs(delta_i) < 1e-9:
            return None
        return self.delta_voltage_v / delta_i

    @property
    def dynamic_loop_mohm(self) -> Optional[float]:
        value = self.dynamic_loop_ohm
        return None if value is None else value * 1000.0

    @property
    def comparable_key(self) -> Optional[str]:
        """Only probes with the same non-empty connection id are directly comparable."""
        connection = self.connection_id.strip()
        return f"{self.battery_id}:{connection}" if connection else None
