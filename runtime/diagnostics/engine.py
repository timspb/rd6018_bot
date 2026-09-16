"""Pure V3 battery diagnostic report builder."""

from __future__ import annotations

from .authority import determine_authority
from .bank_fault import BankFaultEvidence, BankFaultLevel, BankFaultPolicy, score_bank_fault
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

    def evaluate(
        self,
        evidence: BatteryDiagnosticEvidence,
        *,
        bank_fault: BankFaultEvidence | None = None,
        bank_policy: BankFaultPolicy | None = None,
    ) -> BatteryDiagnosticReport:
        assessments = list(
            HypothesisAssessment(
                hypothesis=DiagnosticHypothesis(item.name),
                level=item.confidence,
                confidence=1.0 if item.quality == "valid" else 0.0,
                evidence_refs=(item.name,),
            )
            for item in evidence.items
            if item.name in {hypothesis.value for hypothesis in DiagnosticHypothesis}
        )
        if bank_fault is not None:
            score, level = score_bank_fault(bank_fault, bank_policy or BankFaultPolicy())
            level_map = {
                BankFaultLevel.STABLE: DiagnosticLevel.NORMAL,
                BankFaultLevel.WATCH: DiagnosticLevel.WATCH,
                BankFaultLevel.PROBABLE: DiagnosticLevel.PROBABLE,
                BankFaultLevel.HIGH: DiagnosticLevel.HIGH,
            }
            assessments.append(HypothesisAssessment(
                DiagnosticHypothesis.CELL_FAULT,
                level_map[level],
                min(1.0, score / max(1.0, (bank_policy or BankFaultPolicy()).high_score)),
                tuple(signal.name for signal in bank_fault.signals if bool(signal.value)),
            ))
        assessments_tuple = tuple(assessments)
        authority = determine_authority(assessments_tuple, cell_fault_confirmed=evidence.cell_fault_confirmed)
        condition = BatteryCondition.DEGRADED if any(
            item.level in {DiagnosticLevel.PROBABLE, DiagnosticLevel.HIGH}
            for item in assessments_tuple
        ) else BatteryCondition.UNKNOWN
        return BatteryDiagnosticReport(
            hypotheses=assessments_tuple,
            condition=condition,
            authority=authority,
            evidence=evidence.items,
        )
