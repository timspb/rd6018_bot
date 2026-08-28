from __future__ import annotations

import logging
import math
import time
from typing import Any, Callable, Dict, Optional

from charge_logic import ChargeController
from first_stage_evidence import FirstStageAssessment, assess_first_stage
from legacy_recipe_adapter import chemistry_for_legacy_profile
from legacy_transition_audit import LegacyTransitionAudit, TransitionAuditSeverity, audit_legacy_transition
from pb_domain import BatteryCondition, ChargeIntent
from recovery_session import RecoveryTracePoint
from recovery_shadow import ShadowRecoveryRuntime

logger = logging.getLogger("rd6018.recovery.shadow")


class ChargeControllerV2(ChargeController):
    """Drop-in legacy controller with a non-actuating V2 evidence sidecar.

    `tick()` remains legacy-authoritative. The V2 stack receives the exact same
    U/I/T sample and records what it *would* decide. Its result is exposed under
    `actions["recovery_shadow"]`; no legacy action is removed or changed.
    """

    def __init__(
        self,
        hass_client: Any,
        notify_cb: Optional[Callable[[str], Any]] = None,
        *,
        battery_id: Optional[str] = None,
        recovery_intent: ChargeIntent = ChargeIntent.RECOVERY,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
    ) -> None:
        super().__init__(hass_client, notify_cb=notify_cb)
        self._v2_battery_id = battery_id
        self._v2_intent = recovery_intent
        self._v2_condition_before = condition_before
        self._v2_runtime: Optional[ShadowRecoveryRuntime] = None
        self._v2_target_voltage_v: Optional[float] = None
        self._v2_last_stage: Optional[str] = None
        self._v2_last_disagreement: Optional[str] = None
        self._v2_disagreement_repeat_count: int = 0

    def configure_recovery_context(
        self,
        *,
        battery_id: str,
        intent: ChargeIntent = ChargeIntent.RECOVERY,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
    ) -> None:
        if self.is_active:
            raise RuntimeError("cannot replace recovery context while charge is active")
        self._v2_battery_id = str(battery_id)
        self._v2_intent = intent
        self._v2_condition_before = condition_before
        self._v2_runtime = None
        self._v2_last_disagreement = None
        self._v2_disagreement_repeat_count = 0

    def _new_runtime(self, *, started_at: float) -> ShadowRecoveryRuntime:
        battery_id = self._v2_battery_id or (
            f"session:{self.battery_type}:{self.ah_capacity}:{int(started_at)}"
        )
        runtime = ShadowRecoveryRuntime(
            battery_id=battery_id,
            started_at=started_at,
            intent=self._v2_intent,
            condition_before=self._v2_condition_before,
        )
        self._v2_runtime = runtime
        return runtime

    def start(self, battery_type: str, ah_capacity: int) -> None:
        super().start(battery_type, ah_capacity)
        started_at = self.total_start_time or time.time()
        self._new_runtime(started_at=started_at)
        self._v2_last_disagreement = None
        self._v2_disagreement_repeat_count = 0
        try:
            target_v, _ = self._get_target_v_i()
            self._v2_target_voltage_v = float(target_v)
        except Exception:
            self._v2_target_voltage_v = None
        self._v2_last_stage = self.current_stage

    @staticmethod
    def _finite_or_nan(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return math.nan
        return parsed if math.isfinite(parsed) else math.nan

    @staticmethod
    def _first_stage_metadata(assessment: FirstStageAssessment) -> Dict[str, Any]:
        return {
            "state": assessment.state.value,
            "current_c_rate": assessment.current_c_rate,
            "tail_threshold_a": assessment.tail_threshold_a,
            "tail_threshold_c": assessment.tail_threshold_c,
            "near_target": assessment.near_target,
            "reason": assessment.reason,
        }

    @staticmethod
    def _transition_audit_metadata(audit: LegacyTransitionAudit) -> Dict[str, Any]:
        return {
            "code": audit.code,
            "severity": audit.severity.value,
            "reason": audit.reason,
            "stage_before": audit.stage_before,
            "stage_after": audit.stage_after,
            "first_stage_state": (
                audit.first_stage_state.value if audit.first_stage_state is not None else None
            ),
        }

    def _shadow_metadata(
        self,
        record: Any,
        *,
        first_stage: Optional[FirstStageAssessment] = None,
        transition_audit: Optional[LegacyTransitionAudit] = None,
    ) -> Dict[str, Any]:
        metrics = record.analysis.metrics
        payload = {
            "decision": record.decision.decision.value,
            "reason": record.decision.reason,
            "events": sorted(event.value for event in record.analysis.events),
            "disagreement": record.disagreement,
            "legacy_effect": record.legacy_effect,
            "metrics": {
                "d_voltage_v_per_min": metrics.d_voltage_v_per_min,
                "d_current_a_per_min": metrics.d_current_a_per_min,
                "d_temp_c_per_min": metrics.d_temp_c_per_min,
                "current_min_a": metrics.current_min_a,
                "seconds_since_current_min": metrics.seconds_since_current_min,
                "delta_current_from_min_a": metrics.delta_current_from_min_a,
                "reversal_confirmations": metrics.reversal_confirmations,
            },
        }
        if first_stage is not None:
            payload["first_stage"] = self._first_stage_metadata(first_stage)
        if transition_audit is not None:
            payload["transition_audit"] = self._transition_audit_metadata(transition_audit)
        return payload

    def _assess_main_sample(
        self,
        *,
        stage_before: str,
        target_before: Optional[float],
        timestamp_s: float,
        voltage: float,
        current: float,
        is_cv: bool,
        record: Any,
    ) -> Optional[FirstStageAssessment]:
        if stage_before != self.STAGE_MAIN or target_before is None:
            return None
        if not math.isfinite(float(target_before)):
            return None

        stuck_since = getattr(self, "_stuck_current_since", None)
        plateau_minutes = 0.0
        if stuck_since is not None:
            plateau_minutes = max(0.0, (timestamp_s - float(stuck_since)) / 60.0)
        required_plateau = 120.0 if self.battery_type == self.PROFILE_AGM else 40.0
        metrics = record.analysis.metrics
        return assess_first_stage(
            chemistry=chemistry_for_legacy_profile(self.battery_type),
            capacity_ah=float(self.ah_capacity),
            voltage_v=self._finite_or_nan(voltage),
            current_a=self._finite_or_nan(current),
            target_voltage_v=float(target_before),
            is_cv=bool(is_cv),
            plateau_minutes=plateau_minutes,
            required_plateau_minutes=required_plateau,
            dtemp_c_per_min=metrics.d_temp_c_per_min,
            dcurrent_a_per_min=metrics.d_current_a_per_min,
            dvoltage_v_per_min=metrics.d_voltage_v_per_min,
        )

    def _log_shadow_disagreement(self, record: Any, *, stage: str) -> None:
        disagreement = record.disagreement
        if disagreement is None:
            self._v2_last_disagreement = None
            self._v2_disagreement_repeat_count = 0
            return

        if disagreement == self._v2_last_disagreement:
            self._v2_disagreement_repeat_count += 1
        else:
            self._v2_last_disagreement = disagreement
            self._v2_disagreement_repeat_count = 1

        # First occurrence is always visible; a persistent disagreement repeats every
        # 20 samples (~10 minutes at the current 30 second production poll interval).
        if self._v2_disagreement_repeat_count != 1 and self._v2_disagreement_repeat_count % 20 != 0:
            return

        logger.warning(
            "RECOVERY_SHADOW disagreement=%s repeats=%d decision=%s legacy=%s "
            "stage=%s reason=%s",
            disagreement,
            self._v2_disagreement_repeat_count,
            record.decision.decision.value,
            record.legacy_effect,
            stage,
            record.decision.reason,
        )

    @staticmethod
    def _log_transition_audit(audit: Optional[LegacyTransitionAudit]) -> None:
        if audit is None:
            return
        log_fn = logger.warning if audit.severity in {
            TransitionAuditSeverity.REVIEW,
            TransitionAuditSeverity.SAFETY,
        } else logger.info
        log_fn(
            "RECOVERY_TRANSITION_AUDIT severity=%s code=%s from=%s to=%s "
            "first_stage=%s reason=%s",
            audit.severity.value,
            audit.code,
            audit.stage_before,
            audit.stage_after,
            audit.first_stage_state.value if audit.first_stage_state is not None else "none",
            audit.reason,
        )

    async def tick(
        self,
        voltage: float,
        current: float,
        temp_ext: Optional[float],
        is_cv: bool,
        ah: float,
        output_is_on: Optional[Any] = None,
        manual_off_active: bool = False,
        is_cc: Optional[bool] = None,
    ) -> Dict[str, Any]:
        # The measurement belongs to the stage/setpoint that was active before
        # legacy tick() potentially performs a transition for the next interval.
        stage_before = self.current_stage
        target_before = self._v2_target_voltage_v

        actions = await super().tick(
            voltage,
            current,
            temp_ext,
            is_cv,
            ah,
            output_is_on,
            manual_off_active=manual_off_active,
            is_cc=is_cc,
        )

        timestamp_s = self.last_update_time or time.time()
        runtime = self._v2_runtime
        if runtime is None:
            runtime = self._new_runtime(started_at=self.total_start_time or timestamp_s)

        record = runtime.observe(
            RecoveryTracePoint(
                timestamp_s=timestamp_s,
                stage=stage_before,
                voltage_v=self._finite_or_nan(voltage),
                current_a=self._finite_or_nan(current),
                temp_c=self._finite_or_nan(temp_ext),
                is_cv=bool(is_cv),
                target_voltage_v=target_before,
                ah=self._finite_or_nan(ah),
            ),
            legacy_actions=actions,
            output_is_on=(
                output_is_on is True or str(output_is_on).lower() == "on"
                if output_is_on is not None
                else None
            ),
        )
        self._log_shadow_disagreement(record, stage=stage_before)
        first_stage = self._assess_main_sample(
            stage_before=stage_before,
            target_before=target_before,
            timestamp_s=timestamp_s,
            voltage=voltage,
            current=current,
            is_cv=is_cv,
            record=record,
        )
        transition_audit = audit_legacy_transition(
            stage_before=stage_before,
            stage_after=self.current_stage,
            first_stage=first_stage,
        )
        self._log_transition_audit(transition_audit)
        actions["recovery_shadow"] = self._shadow_metadata(
            record,
            first_stage=first_stage,
            transition_audit=transition_audit,
        )

        # Setpoints in the returned legacy actions apply to the *next* sample.
        next_target = actions.get("set_voltage")
        if next_target is not None:
            self._v2_target_voltage_v = self._finite_or_nan(next_target)
        elif self.current_stage != stage_before:
            self._v2_target_voltage_v = None
        self._v2_last_stage = self.current_stage
        return actions

    @property
    def recovery_shadow_summary(self) -> Dict[str, Any]:
        if self._v2_runtime is None:
            return {
                "samples": 0,
                "decision_counts": {},
                "disagreement_counts": {},
                "last_disagreement": None,
                "last_disagreement_repeats": 0,
            }
        summary = dict(self._v2_runtime.summary())
        summary["last_disagreement"] = self._v2_last_disagreement
        summary["last_disagreement_repeats"] = self._v2_disagreement_repeat_count
        return summary
