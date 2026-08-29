from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional

from battery_diagnostics import DiagnosticHypothesis, assess_specific_gravity
from battery_diagnostics_store import list_specific_gravity
from battery_fault_engine import (
    BatteryFaultAssessment,
    BatteryFaultContext,
    DiagnosticAuthority,
    assess_battery_fault,
)
from charge_logic import AGM_STAGES
from first_stage_evidence import FirstStageAssessment, FirstStageState
from pb_domain import ChargeIntent
from production_controller import ProductionChargeControllerV2
from v2_authority import AuthorityAction, AuthorityDecision


_RECOVERY_INTENTS = frozenset({ChargeIntent.RECOVERY, ChargeIntent.CONDITIONING})


class DiagnosticProductionChargeControllerV2(ProductionChargeControllerV2):
    """Production V2 with hypothesis-specific diagnostic evidence.

    Diagnostic inference never emits HARD_STOP.  It may veto a *new automatic HV
    escalation* only when the fault engine returns BLOCK_AUTOMATIC_HV.  Hard safety
    remains the independent U/I/T/protection/readback/watchdog layer.
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
            # Diagnostic storage is auxiliary evidence. A DB/read failure must not
            # masquerade as battery evidence or invalidate the deterministic controller.
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

    def _next_main_transition_is_hv(
        self,
        first_stage: Optional[FirstStageAssessment],
    ) -> bool:
        if first_stage is None or self._v2_intent not in _RECOVERY_INTENTS:
            return False
        if first_stage.state is FirstStageState.STUCK_PLATEAU:
            return True
        if first_stage.state is not FirstStageState.TAIL_READY:
            return False
        if self.battery_type == self.PROFILE_AGM and self._agm_stage_idx < len(AGM_STAGES) - 1:
            return False
        return True

    def _diagnostic_hv_veto(
        self,
        first_stage: Optional[FirstStageAssessment],
    ) -> Optional[AuthorityDecision]:
        if not self._next_main_transition_is_hv(first_stage):
            return None
        if self._diagnostic_assessment.authority is not DiagnosticAuthority.BLOCK_AUTOMATIC_HV:
            return None
        reasons = ",".join(self._diagnostic_assessment.authority_reasons) or "cell_fault_block"
        return AuthorityDecision(
            AuthorityAction.STOP_AND_DIAGNOSE,
            f"diagnostic_hv_block:{reasons}",
        )

    def _apply_authoritative_decision(
        self,
        *,
        record: Any,
        first_stage: Optional[FirstStageAssessment],
        stage_before: str,
        timestamp_s: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        is_cv: bool,
        is_cc: bool,
        actions: Dict[str, Any],
    ) -> Optional[AuthorityDecision]:
        self._update_live_diagnostic_evidence(
            timestamp_s=timestamp_s,
            voltage=voltage,
            current=current,
            temp=temp,
            ah=ah,
        )
        veto = self._diagnostic_hv_veto(first_stage)
        if veto is not None and stage_before == self.STAGE_MAIN and self.current_stage == stage_before:
            self._stop_and_diagnose(
                actions=actions,
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=veto.reason,
            )
            actions["battery_diagnostics"] = self.diagnostic_snapshot()
            return veto

        decision = super()._apply_authoritative_decision(
            record=record,
            first_stage=first_stage,
            stage_before=stage_before,
            timestamp_s=timestamp_s,
            voltage=voltage,
            current=current,
            temp=temp,
            ah=ah,
            is_cv=is_cv,
            is_cc=is_cc,
            actions=actions,
        )
        actions["battery_diagnostics"] = self.diagnostic_snapshot()
        return decision

    async def tick(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        await self._refresh_stored_diagnostics()
        return await super().tick(*args, **kwargs)
