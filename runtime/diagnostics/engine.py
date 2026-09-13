"""Pure V3 battery diagnostic report builder."""

from __future__ import annotations

from .authority import determine_authority
from .models import (
    BatteryCondition,
    BatteryDiagnosticEvidence,
    BatteryDiagnosticReport,
    DiagnosticHypothesis,
    DiagnosticLevel,
    HypothesisAssessment,
)


class BatteryDiagnosticsEngine:
    """Consumes facts and produces a report; it never controls output."""

    def evaluate(self, evidence: BatteryDiagnosticEvidence) -> BatteryDiagnosticReport:
        assessments = tuple(
            HypothesisAssessment(
                hypothesis=DiagnosticHypothesis(item.name),
                level=item.confidence,
                confidence=1.0 if item.quality == "valid" else 0.0,
                evidence_refs=(item.name,),
            )
            for item in evidence.items
            if item.name in {hypothesis.value for hypothesis in DiagnosticHypothesis}
        )
        authority = determine_authority(assessments, cell_fault_confirmed=evidence.cell_fault_confirmed)
        condition = BatteryCondition.DEGRADED if any(
            item.level in {DiagnosticLevel.PROBABLE, DiagnosticLevel.HIGH}
            for item in assessments
        ) else BatteryCondition.UNKNOWN
        return BatteryDiagnosticReport(
            hypotheses=assessments,
            condition=condition,
            authority=authority,
            evidence=evidence.items,
        )
