from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from first_stage_evidence import FirstStageAssessment, FirstStageState


class TransitionAuditSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    SAFETY = "safety"


@dataclass(frozen=True)
class LegacyTransitionAudit:
    code: str
    severity: TransitionAuditSeverity
    reason: str
    stage_before: str
    stage_after: str
    first_stage_state: Optional[FirstStageState]


MAIN_NAMES = frozenset({"main", "main charge", "bulk", "absorption"})
HV_NAMES = frozenset(
    {
        "mix",
        "mix mode",
        "desulfation",
        "десульфатация",
        "conditioning",
        "recovery",
    }
)

# A persistent Main CV plateau is useful recovery evidence, but its magnitude still
# matters. Above ~1%C it is no longer a low tail phenomenon; keep that case visible
# for review instead of giving every STUCK_PLATEAU the same benign INFO label.
# This is diagnostic only and does not authorize or block an HV recipe.
HIGH_PLATEAU_REVIEW_C_RATE = 0.010


def _stage_key(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def audit_legacy_transition(
    *,
    stage_before: str,
    stage_after: str,
    first_stage: Optional[FirstStageAssessment],
) -> Optional[LegacyTransitionAudit]:
    """Audit legacy state movement without altering it.

    The important transition is Main -> a higher-voltage recovery stage. A fixed
    absolute-current timer may still make that move today. V2 records whether the
    same sample actually looked like a stable CV plateau, or whether it carried
    evidence that should have prevented escalation.
    """
    before = _stage_key(stage_before)
    after = _stage_key(stage_after)
    if before not in MAIN_NAMES or after not in HV_NAMES:
        return None

    if first_stage is None:
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_without_v2_evidence",
            severity=TransitionAuditSeverity.REVIEW,
            reason="Main->HV occurred before a V2 first-stage assessment was available",
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=None,
        )

    state = first_stage.state
    if state == FirstStageState.THERMALLY_UNSTABLE:
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_during_thermal_instability",
            severity=TransitionAuditSeverity.SAFETY,
            reason=first_stage.reason,
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=state,
        )
    if state == FirstStageState.VOLTAGE_UNSTABLE:
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_during_voltage_instability",
            severity=TransitionAuditSeverity.SAFETY,
            reason=first_stage.reason,
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=state,
        )
    if state == FirstStageState.TELEMETRY_INVALID:
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_with_invalid_evidence",
            severity=TransitionAuditSeverity.SAFETY,
            reason=first_stage.reason,
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=state,
        )
    if state == FirstStageState.BULK_OR_TAPER:
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_while_tail_evolving",
            severity=TransitionAuditSeverity.REVIEW,
            reason=first_stage.reason,
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=state,
        )
    if state == FirstStageState.TAIL_READY:
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_after_tail_ready",
            severity=TransitionAuditSeverity.INFO,
            reason=(
                "Main tail is low and stable enough to review recovery-stage eligibility; "
                "this is not by itself proof that HV recovery is required"
            ),
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=state,
        )
    if state == FirstStageState.STUCK_PLATEAU:
        c_rate = first_stage.current_c_rate
        if c_rate is not None and c_rate > HIGH_PLATEAU_REVIEW_C_RATE:
            return LegacyTransitionAudit(
                code="legacy_hv_escalation_after_high_c_rate_plateau",
                severity=TransitionAuditSeverity.REVIEW,
                reason=(
                    f"persistent Main CV plateau is still high at {c_rate:.4f}C; "
                    "review battery condition and recovery eligibility before treating "
                    "this as an ordinary low-tail plateau"
                ),
                stage_before=stage_before,
                stage_after=stage_after,
                first_stage_state=state,
            )
        return LegacyTransitionAudit(
            code="legacy_hv_escalation_after_stuck_plateau",
            severity=TransitionAuditSeverity.INFO,
            reason=(
                "V2 also sees a persistent CV plateau at a moderate C-rate; "
                "chemistry/intent/condition still determine whether an HV recovery "
                "recipe is appropriate"
            ),
            stage_before=stage_before,
            stage_after=stage_after,
            first_stage_state=state,
        )
    return None
