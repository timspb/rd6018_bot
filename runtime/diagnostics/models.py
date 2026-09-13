"""Data-only battery diagnostic contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class DiagnosticAuthority(str, Enum):
    ALLOW = "allow"
    VERIFY_BEFORE_HV = "verify_before_hv"
    BLOCK_AUTOMATIC_HV = "block_automatic_hv"
    HARD_STOP = "hard_stop"


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


class BatteryCondition(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    SULFATED_SUSPECTED = "sulfated_suspected"
    DRY_SUSPECTED = "dry_suspected"
    REHYDRATED = "rehydrated"
    OVERWET_SUSPECTED = "overwet_suspected"
    STRATIFIED_SUSPECTED = "stratified_suspected"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class DiagnosticEvidenceItem:
    """One observable fact; not an interpretation or actuator command."""

    name: str
    value: object
    timestamp: float
    source: str
    confidence: DiagnosticLevel = DiagnosticLevel.NORMAL
    quality: str = "valid"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.source.strip():
            raise ValueError("evidence name and source are required")
        if not math.isfinite(float(self.timestamp)):
            raise ValueError("evidence timestamp must be finite")
        if not self.quality.strip():
            raise ValueError("evidence quality is required")


@dataclass(frozen=True)
class HypothesisAssessment:
    hypothesis: DiagnosticHypothesis
    level: DiagnosticLevel
    confidence: float
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("hypothesis confidence must be between 0 and 1")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("hypothesis evidence references must be non-empty")


@dataclass(frozen=True)
class BatteryDiagnosticEvidence:
    """Evidence supplied by telemetry/diagnostic collectors."""

    cell_fault_confirmed: bool = False
    evidence_ids: tuple[str, ...] = ()
    source: str = "telemetry"
    items: tuple[DiagnosticEvidenceItem, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("diagnostic evidence source is required")
        if any(not item.strip() for item in self.evidence_ids):
            raise ValueError("diagnostic evidence ids must be non-empty")
        if self.cell_fault_confirmed and not self.evidence_ids:
            raise ValueError("confirmed cell fault requires evidence ids")


@dataclass(frozen=True)
class DiagnosticDecision:
    authority: DiagnosticAuthority
    reasons: tuple[str, ...] = ()
    hypothesis: str | None = None

    @property
    def hard_stop(self) -> bool:
        return self.authority is DiagnosticAuthority.HARD_STOP


@dataclass(frozen=True)
class BatteryDiagnosticReport:
    """Domain report consumed by Safety as evidence, never by an actuator."""

    hypotheses: tuple[HypothesisAssessment, ...] = ()
    condition: BatteryCondition = BatteryCondition.UNKNOWN
    authority: DiagnosticDecision = DiagnosticDecision(DiagnosticAuthority.ALLOW)
    evidence: tuple[DiagnosticEvidenceItem, ...] = ()
