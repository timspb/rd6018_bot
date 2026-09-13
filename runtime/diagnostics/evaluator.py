"""Translate explicit diagnostic evidence into safety authority."""

from __future__ import annotations

from .models import BatteryDiagnosticEvidence, DiagnosticAuthority, DiagnosticDecision


def evaluate_battery_diagnostics(evidence: BatteryDiagnosticEvidence) -> DiagnosticDecision:
    if evidence.cell_fault_confirmed:
        return DiagnosticDecision(
            DiagnosticAuthority.HARD_STOP,
            ("confirmed cell fault: " + ",".join(evidence.evidence_ids),),
            "CELL_FAULT",
        )
    return DiagnosticDecision(DiagnosticAuthority.ALLOW)
