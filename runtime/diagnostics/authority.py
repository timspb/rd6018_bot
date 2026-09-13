"""Pure mapping from diagnostic findings to authority."""

from __future__ import annotations

from .models import (
    DiagnosticAuthority,
    DiagnosticDecision,
    DiagnosticHypothesis,
    DiagnosticLevel,
    HypothesisAssessment,
)


def determine_authority(
    hypotheses: tuple[HypothesisAssessment, ...],
    *,
    cell_fault_confirmed: bool = False,
) -> DiagnosticDecision:
    """Map explicit evidence to authority; do not issue a stop command."""
    if cell_fault_confirmed:
        return DiagnosticDecision(
            DiagnosticAuthority.HARD_STOP,
            ("cell_fault_confirmed",),
            DiagnosticHypothesis.CELL_FAULT.value,
        )
    cell = next((item for item in hypotheses if item.hypothesis is DiagnosticHypothesis.CELL_FAULT), None)
    thermal = next((item for item in hypotheses if item.hypothesis is DiagnosticHypothesis.THERMAL_ABNORMALITY), None)
    if cell and cell.level is DiagnosticLevel.HIGH:
        return DiagnosticDecision(DiagnosticAuthority.BLOCK_AUTOMATIC_HV, ("cell_fault_high_confidence",), cell.hypothesis.value)
    if (cell and cell.level in {DiagnosticLevel.PROBABLE, DiagnosticLevel.HIGH}) or (thermal and thermal.level in {DiagnosticLevel.PROBABLE, DiagnosticLevel.HIGH}):
        return DiagnosticDecision(DiagnosticAuthority.VERIFY_BEFORE_HV, ("fault_requires_verification",), (cell or thermal).hypothesis.value)
    return DiagnosticDecision(DiagnosticAuthority.ALLOW)
