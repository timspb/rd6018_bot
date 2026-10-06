"""Compatibility import surface for first-stage evidence.

Canonical ownership lives in runtime.charge.evidence.first_stage and its
module-local variables. Production code should import the canonical module.
"""

from runtime.charge.evidence.first_stage import (
    FirstStageAssessment,
    FirstStageState,
    assess_first_stage,
    tail_c_rate,
    tail_current_threshold_a,
)

__all__ = [
    "FirstStageAssessment",
    "FirstStageState",
    "assess_first_stage",
    "tail_c_rate",
    "tail_current_threshold_a",
]
