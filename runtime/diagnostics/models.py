"""Data-only battery diagnostic contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiagnosticAuthority(str, Enum):
    ALLOW = "allow"
    VERIFY_BEFORE_HV = "verify_before_hv"
    BLOCK_AUTOMATIC_HV = "block_automatic_hv"
    HARD_STOP = "hard_stop"


@dataclass(frozen=True)
class BatteryDiagnosticEvidence:
    """Evidence supplied by telemetry/diagnostic collectors."""

    cell_fault_confirmed: bool = False
    evidence_ids: tuple[str, ...] = ()
    source: str = "telemetry"

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
