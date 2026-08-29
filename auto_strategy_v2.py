from __future__ import annotations

import time
from typing import Any, Dict, Optional

from charge_logic import (
    AGM_FIRST_STAGE_HOLD_SEC,
    AGM_STAGES,
    ANTISULFATE_MAX_AGM,
    ANTISULFATE_MAX_CA_EFB,
    FIRST_STAGE_HOLD_SEC,
    MAIN_STAGE_MAX_HOURS,
)
from first_stage_evidence import FirstStageAssessment
from production_controller import ProductionChargeControllerV2
from v2_authority import AuthorityAction, AuthorityDecision, decide_main_transition


class AutoStrategyProductionChargeControllerV2(ProductionChargeControllerV2):
    """Production AUTO strategy after the V1 behavioral audit.

    This layer deliberately owns Main's strategy timeout so the legacy scaffold cannot
    turn the accepted 72 h fallback into an unrelated hard OFF before V2 authority sees
    it. It also keeps production/UI timing consistent with the accepted 20/24/10 h Mix
    windows while the byte-for-byte-ish rollback scaffold retains historical constants.
    """

    _OPERATOR_REASON_TEXT = {
        **ProductionChargeControllerV2._OPERATOR_REASON_TEXT,
        "main_tail_hold_complete_standard_mix": (
            "Основной заряд завершён по хвосту; начинается штатный Mix."
        ),
        "main_tail_hold_complete_diagnostic_no_hv": (
            "Основной заряд завершён; Diagnostic не разрешает автоматический HV."
        ),
        "persistent_main_plateau_diagnostic_no_hv": (
            "Подтверждена устойчивая полка; Diagnostic остановлен для анализа без HV."
        ),
        "main_timeout_ca_efb_v1_compatible_mix": (
            "Достигнут 72-часовой fallback Main; Ca/EFB продолжает штатным Mix."
        ),
        "agm_main_timeout_low_current_cv_mix": (
            "AGM достиг 72-часового fallback уже в CV с I≤0.2 A; разрешён финальный Mix."
        ),
        "agm_main_timeout_without_low_current_tail": (
            "AGM достиг 72 часов без безопасного низкотокового хвоста; требуется диагностика."
        ),
        "agm_recovery_budget_exhausted_wait_for_tail": (
            "AGM исчерпал сервисные recovery-попытки; остаёмся в Main и ждём нормальный хвост."
        ),
    }

    async def _run_legacy_scaffold_tick(
        self,
        *,
        stage_before: str,
        voltage: float,
        current: float,
        temp_ext: Optional[float],
        is_cv: bool,
        ah: float,
        output_is_on: Optional[Any],
        manual_off_active: bool,
        is_cc: Optional[bool],
    ) -> Dict[str, Any]:
        if not (
            self._is_authoritative_stage(stage_before)
            and stage_before == self.STAGE_MAIN
        ):
            return await super()._run_legacy_scaffold_tick(
                stage_before=stage_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                ah=ah,
                output_is_on=output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
            )

        # Hide only Main elapsed time from the legacy scaffold. All actual safety
        # checks still execute there. The real stage clock is restored before V2
        # authority evaluates the explicit strategy fallback below.
        real_stage_start = self.stage_start_time
        self.stage_start_time = time.time()
        try:
            return await super()._run_legacy_scaffold_tick(
                stage_before=stage_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                ah=ah,
                output_is_on=output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
            )
        finally:
            if self.current_stage == stage_before:
                self.stage_start_time = real_stage_start

    def _decide_main_authority(
        self,
        *,
        record: Any,
        first_stage: Optional[FirstStageAssessment],
        timestamp_s: float,
        current: float,
        is_cv: bool,
    ) -> AuthorityDecision:
        required_hold = (
            AGM_FIRST_STAGE_HOLD_SEC
            if self.battery_type == self.PROFILE_AGM
            else FIRST_STAGE_HOLD_SEC
        )
        max_desulf = (
            ANTISULFATE_MAX_AGM
            if self.battery_type == self.PROFILE_AGM
            else ANTISULFATE_MAX_CA_EFB
        )
        return decide_main_transition(
            profile=self.battery_type,
            intent=self._v2_intent,
            first_stage=first_stage,
            policy_decision=record.decision.decision,
            seconds_since_current_min=record.analysis.metrics.seconds_since_current_min,
            required_tail_hold_s=required_hold,
            agm_stage_idx=self._agm_stage_idx,
            agm_stage_count=len(AGM_STAGES),
            desulf_attempts=self.antisulfate_count,
            max_desulf_attempts=max_desulf,
            main_elapsed_s=max(0.0, float(timestamp_s) - float(self.stage_start_time)),
            main_limit_s=float(MAIN_STAGE_MAX_HOURS) * 3600.0,
            current_a=float(current),
            is_cv=bool(is_cv),
        )

    def _apply_main_authority_decision(
        self,
        decision: AuthorityDecision,
        *,
        actions: Dict[str, Any],
        timestamp_s: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
    ) -> AuthorityDecision:
        if decision.action == AuthorityAction.ADVANCE_AGM_STEP:
            self._advance_agm_step(
                actions=actions,
                now=timestamp_s,
                temp=temp,
                ah=ah,
                reason=decision.reason,
            )
        elif decision.action == AuthorityAction.ENTER_DESULFATION:
            self._enter_desulfation(
                actions=actions,
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=decision.reason,
            )
        elif decision.action == AuthorityAction.ENTER_MIX:
            self._enter_mix(
                actions=actions,
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=decision.reason,
            )
        elif decision.action == AuthorityAction.COMPLETE_TO_SAFE_WAIT:
            self._enter_safe_wait_done(
                actions=actions,
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=decision.reason,
            )
        elif decision.action == AuthorityAction.STOP_AND_DIAGNOSE:
            self._stop_and_diagnose(
                actions=actions,
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=decision.reason,
            )
        return decision

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
        if stage_before == self.STAGE_MAIN and self._is_authoritative_stage(stage_before):
            if self.current_stage != stage_before:
                return None
            decision = self._decide_main_authority(
                record=record,
                first_stage=first_stage,
                timestamp_s=timestamp_s,
                current=current,
                is_cv=is_cv,
            )
            return self._apply_main_authority_decision(
                decision,
                actions=actions,
                timestamp_s=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
            )
        return super()._apply_authoritative_decision(
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

    def _get_stage_max_hours(self) -> Optional[float]:
        if self.current_stage == self.STAGE_MIX and self.finish_timer_start is None:
            return self._mix_limit_seconds() / 3600.0
        return super()._get_stage_max_hours()

    def get_timers(self) -> Dict[str, Any]:
        timers = super().get_timers()
        if self.current_stage == self.STAGE_MIX and self.finish_timer_start is None:
            now = time.time()
            limit_s = self._mix_limit_seconds()
            elapsed = max(0.0, now - self.stage_start_time)
            remaining = max(0.0, limit_s - elapsed)
            timers["stage_limit_sec"] = limit_s
            timers["stage_elapsed_sec"] = elapsed
            timers["remaining_time"] = (
                f"{int(remaining // 3600):02d}:{int((remaining % 3600) // 60):02d}"
                if remaining > 0
                else "00:00"
            )
        return timers

    def _session_rules_summary(self) -> str:
        if self.battery_type == self.PROFILE_CA:
            return "Main 14.7V; recovery budget 3/session; Mix 16.5V/20h; SafeWait 2h."
        if self.battery_type == self.PROFILE_EFB:
            return "Main 14.8V; recovery budget 3/session; Mix 16.5V/24h; SafeWait 2h."
        if self.battery_type == self.PROFILE_AGM:
            return "Main 14.4/14.6/14.8/15.0V; recovery budget 4/session; Mix 16.3V/10h; SafeWait 2h."
        return super()._session_rules_summary()

    def get_ai_stage_snapshot(self, temp_c: Optional[float] = None) -> Dict[str, Any]:
        snapshot = super().get_ai_stage_snapshot(temp_c)
        if (
            self.current_stage == self.STAGE_MIX
            and self.finish_timer_start is None
            and self.battery_type == self.PROFILE_EFB
        ):
            snapshot["summary"] = "Mix 16.5V / 0.03C: normal exit by ΔV/ΔI; 24h fallback."
            snapshot["transition"] = "Normal exit by ΔV/ΔI; without delta, 24h fallback -> SAFE_WAIT."
            policy = snapshot.get("mix_exit_policy")
            if isinstance(policy, dict):
                policy["fallback_limit_hours"] = 24.0
        return snapshot
