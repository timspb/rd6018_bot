from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional

from auto_strategy import AutoStrategyProductionChargeController
from battery_diagnostics import assess_specific_gravity
from battery_diagnostics_store import list_specific_gravity
from battery_fault_engine import (
    BatteryFaultAssessment,
    BatteryFaultContext,
    DiagnosticAuthority,
    assess_battery_fault,
)
from runtime.charge.evidence.first_stage import FirstStageAssessment
from mix_active_authority import MixActiveAuthorityMixin
from runtime.charge.decisions import AuthorityAction, AuthorityDecision


_HV_ACTIONS = frozenset({AuthorityAction.ENTER_DESULFATION, AuthorityAction.ENTER_MIX})


class DiagnosticProductionChargeController(
    MixActiveAuthorityMixin,
    AutoStrategyProductionChargeController,
):
    """Production AUTO controller with hypothesis-specific diagnostic evidence.

    Diagnostic inference never emits HARD_STOP. It can veto a *new* automatic HV
    transition only when the fault engine returns BLOCK_AUTOMATIC_HV. The decision is
    inspected before the transition is applied, including Normal and 72 h fallbacks.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._diagnostic_context = BatteryFaultContext()
        self._diagnostic_assessment = assess_battery_fault(self._diagnostic_context)
        self._diagnostic_loaded_sg_key: Optional[tuple[str, float]] = None

    @property
    def battery_fault_assessment(self) -> BatteryFaultAssessment:
        return self._diagnostic_assessment

    def update_diagnostic_context(self, **changes: Any) -> BatteryFaultAssessment:
        self._diagnostic_context = replace(self._diagnostic_context, **changes)
        self._diagnostic_assessment = assess_battery_fault(self._diagnostic_context)
        return self._diagnostic_assessment

    async def _refresh_stored_diagnostics(self) -> None:
        battery_id = str(self._v2_battery_id or "").strip()
        if not battery_id:
            return
        try:
            measurements = await list_specific_gravity(battery_id, limit=1)
        except Exception:
            return
        if not measurements:
            return
        latest = measurements[-1]
        key = (battery_id, float(latest.measured_at))
        if key == self._diagnostic_loaded_sg_key:
            return
        assessment = assess_specific_gravity(latest)
        context_name = latest.context.strip().lower().replace("-", "_").replace(" ", "_")
        persisted_after_corrective = context_name in {
            "post_corrective_equalization",
            "after_corrective_equalization",
            "post_equalization_retest",
        }
        self._diagnostic_loaded_sg_key = key
        self.update_diagnostic_context(
            specific_gravity=assessment,
            sg_persisted_after_corrective_equalization=persisted_after_corrective,
        )

    def _update_live_diagnostic_evidence(
        self,
        *,
        timestamp_s: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
    ) -> None:
        try:
            legacy = self._bank_fault_risk_snapshot(
                timestamp_s,
                voltage,
                current,
                temp,
                ah,
            ) or {}
        except Exception:
            legacy = {}
        self.update_diagnostic_context(
            legacy_risk_score=int(legacy.get("score") or 0),
            legacy_risk_status=str(legacy.get("status") or "stable"),
            recovery_attempts=int(self.antisulfate_count),
        )

    def diagnostic_snapshot(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "authority": self._diagnostic_assessment.authority.value,
            "authority_reasons": list(self._diagnostic_assessment.authority_reasons),
            "cell_fault_classes": sorted(self._diagnostic_assessment.independent_cell_fault_classes),
            "hypotheses": {},
        }
        for hypothesis, evidence in self._diagnostic_assessment.hypotheses.items():
            result["hypotheses"][hypothesis.value] = {
                "score": evidence.score,
                "level": evidence.level.value,
                "reasons": list(evidence.reasons),
            }
        return result

    def _diagnostic_hv_veto(self, decision: AuthorityDecision) -> Optional[AuthorityDecision]:
        if decision.action not in _HV_ACTIONS:
            return None
        if self._diagnostic_assessment.authority is not DiagnosticAuthority.BLOCK_AUTOMATIC_HV:
            return None
        reasons = ",".join(self._diagnostic_assessment.authority_reasons) or "cell_fault_block"
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            f"diagnostic_hv_block:{reasons}",
        )
