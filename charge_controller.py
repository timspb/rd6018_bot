from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Callable, Dict, Optional, Tuple

from runtime.charge.controller_state import (
    PROFILE_AGM,
    PROFILE_CA,
    PROFILE_CUSTOM,
    PROFILE_EFB,
    STAGE_COOLING,
    STAGE_DESULFATION,
    STAGE_DONE,
    STAGE_IDLE,
    STAGE_MAIN,
    STAGE_MIX,
    STAGE_PREP,
    STAGE_SAFE_WAIT,
    clear_restored_targets,
    initialize_controller_state,
    reset_bank_fault_state,
    reset_delta_and_blanking,
    reset_link_loss_state,
    reset_stage_metrics,
)
from runtime.charge.sample_state import mark_stage_sample
from runtime.charge.lifecycle import (
    full_reset as full_reset_charge,
    initialize_session,
    reset_session_data as reset_charge_session_data,
    start_charge,
    start_custom_charge,
    stop_charge,
)
from runtime.charge.persistence import (
    SESSION_FILE,
    SESSION_START_MAX_AGE_S,
    TerminalPersistenceRequest,
    clear_session_file,
    enrich_restored_session,
    restore_session,
    save_session,
)
from runtime.charge.session import apply_trace_identity, new_trace_identity, set_current_stage
from runtime.charge.post import post_charge_profile_params
from runtime.charge.session_continuation_restore import (
    restore_final_safe_wait,
    restore_recovery_safe_wait,
)

SESSION_START_MAX_AGE = SESSION_START_MAX_AGE_S
from runtime.charge.evidence.first_stage import (
    FirstStageAssessment,
    FirstStageState,
    MainSampleEvidenceEvaluator,
    MainSampleEvidenceInput,
)
from runtime.charge.evidence.trace_context import (
    TraceLifecycle,
    SignalContextInput,
    TracePointInput,
    build_shadow_metadata,
    build_signal_context,
    build_trace_point_metadata,
    finite_or_nan,
    normalize_output_on,
    recovery_trace_context as build_recovery_trace_context,
)
from application.recipe_policy import chemistry_for_profile
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision
from recovery_session import RecoveryTracePoint
from recovery_shadow import ShadowRecoveryRuntime
from signal_analyzer import SignalEvent
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.diagnostics import (
    ai_stage_snapshot,
    bank_fault_risk_snapshot,
    get_timers as diagnostic_timers,
)
from runtime.charge.runtime.main_scaffold import (
    apply_main_authority_tick,
    run_authoritative_main_scaffold,
)
from runtime.charge.runtime.desulfation_completion import (
    complete_desulfation_to_safe_wait,
)
from runtime.charge.runtime.support import (
    current_targets,
    exit_cc_condition,
    exit_cv_condition,
    mix_current_delta_threshold,
    session_rules_summary,
    stage_max_hours,
    target_finish_time,
)
from runtime.charge.runtime.variables import DELTA_MONITOR_DELAY_S, STAGE_TRANSITION_BLANKING_S
from runtime.charge.runtime.mix_scaffold import (
    apply_mix_authority_tick,
    run_authoritative_mix_scaffold,
)
from runtime.charge.runtime.final_safe_wait_completion import (
    FinalSafeWaitCompletionInput,
    apply_final_safe_wait_completion_effect,
    build_final_safe_wait_completion_effect,
)
from runtime.charge.runtime.final_safe_wait_authority import (
    build_final_safe_wait_authority_effect,
)
from runtime.charge.runtime.recovery_scaffold import run_authoritative_recovery_scaffold
from runtime.charge.runtime.residual_scaffold import run_authoritative_residual_scaffold
from runtime.charge.runtime.stop_diagnose import apply_stop_and_diagnose
from runtime.charge.strategy.desulfation import (
    DesulfationAction,
    decide_desulfation,
    select_desulfation_target,
)
from runtime.charge.strategy.desulfation_variables import (
    DESULFATION_OCP_MARGIN_A,
    desulfation_duration_seconds,
)
from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitAction,
    FinalSafeWaitContinuation,
    validate_final_continuation,
)
from runtime.charge.strategy.main_targets import select_main_target
from runtime.charge.strategy.prep import select_prep_target
from runtime.charge.strategy.mix import select_mix_target
from runtime.charge.strategy.mix_variables import (
    mix_max_active_seconds,
)
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitAction,
    RecoverySafeWaitContinuation,
    decide_recovery_safe_wait,
    validate_recovery_continuation,
)
from runtime.charge.strategy.safe_wait_variables import (
    safe_wait_max_seconds,
)
from runtime.charge.strategy.storage import select_storage_target
from runtime.charge.strategy.temperature_variables import (
    AGM_COMPENSATION_V_PER_C,
    CA_EFB_COMPENSATION_V_PER_C,
    CUSTOM_COMPENSATION_V_PER_C,
    TEMPERATURE_MAX_DELTA_V,
    TEMPERATURE_REFERENCE_C,
)
from runtime.safety.variables import (
    MAX_STAGE_CURRENT_A,
    PROTECTION_OCP_MARGIN_A,
    PROTECTION_OVP_MARGIN_V,
)
from runtime.safety.voltage_variables import clamp_pb_automatic_target_voltage
from runtime.charge.strategy.main_variables import (
    AGM_PLATEAU_REQUIRED_MINUTES,
    PLATEAU_EVIDENCE_WINDOW_MINUTES,
    STANDARD_PLATEAU_REQUIRED_MINUTES,
)
logger = logging.getLogger("rd6018.recovery")


# Compatibility alias for existing imports/tests; the semantic owner is modular.
INTERMEDIATE_RECOVERY_DURATION_SEC = desulfation_duration_seconds()


class ManagedChargeController:
    """Transitional production controller while modular V3 replaces the old FSM.

    For non-Custom automatic charging, MAIN, bounded DESULFATION, recovery
    SAFE_WAIT, MIX, and final SAFE_WAIT now use modular strategy/runtime owners and
    do not enter historical ``ChargeController.tick()``. Controller state,
    persistence, lifecycle, diagnostics, target selection, and safety helpers
    are now owned by modular V3 boundaries rather than historical inheritance.

    Production authority is unconditionally modular. Historical transition
    ownership and runtime rollback switches are retired. Custom is owned by the
    managed Manual path and cannot re-enter this controller.
    """

    STAGE_PREP = STAGE_PREP
    STAGE_MAIN = STAGE_MAIN
    STAGE_DESULFATION = STAGE_DESULFATION
    STAGE_MIX = STAGE_MIX
    STAGE_SAFE_WAIT = STAGE_SAFE_WAIT
    STAGE_COOLING = STAGE_COOLING
    STAGE_DONE = STAGE_DONE
    STAGE_IDLE = STAGE_IDLE

    PROFILE_CA = PROFILE_CA
    PROFILE_EFB = PROFILE_EFB
    PROFILE_AGM = PROFILE_AGM
    PROFILE_CUSTOM = PROFILE_CUSTOM

    def __init__(
        self,
        hass_client: Any,
        notify_cb: Optional[Callable[[str], Any]] = None,
        *,
        battery_id: Optional[str] = None,
        recovery_intent: ChargeIntent = ChargeIntent.RECOVERY,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
    ) -> None:
        initialize_controller_state(self, hass_client, notify_cb=notify_cb)
        self._v2_battery_id = battery_id
        self._v2_intent = recovery_intent
        self._v2_condition_before = condition_before
        self._v2_runtime: Optional[ShadowRecoveryRuntime] = None
        self._v2_target_voltage_v: Optional[float] = None
        self._v2_last_stage: Optional[str] = None
        self._trace_lifecycle = TraceLifecycle()
        self._v2_trace_session_id: Optional[str] = None
        self._v2_trace_started_at: float = 0.0
        self._main_sample_evidence = MainSampleEvidenceEvaluator()
        self._recovery_safe_wait: Optional[RecoverySafeWaitContinuation] = None
        self._final_safe_wait: Optional[FinalSafeWaitContinuation] = None
        # Captured by the modular tick and serialized by the production controller.
        self._v2_session_signal_context: Optional[Dict[str, Any]] = None

    @property
    def current_stage(self) -> str:
        return getattr(self, "_current_stage", self.STAGE_IDLE)

    @current_stage.setter
    def current_stage(self, value: str) -> None:
        set_current_stage(self, value)

    @property
    def is_active(self) -> bool:
        return self.current_stage not in (self.STAGE_IDLE, self.STAGE_DONE)

    def _mark_stage_sample(
        self,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
    ) -> None:
        mark_stage_sample(self, voltage, current, temp, ah)

    def _reset_stage_metrics(self) -> None:
        reset_stage_metrics(self)

    def _reset_bank_fault_state(self) -> None:
        reset_bank_fault_state(self)

    def _reset_link_loss_state(self) -> None:
        reset_link_loss_state(self)

    def _clear_restored_targets(self) -> None:
        clear_restored_targets(self)

    def _reset_delta_and_blanking(self, now: float) -> None:
        reset_delta_and_blanking(
            self,
            now,
            delay_s=float(DELTA_MONITOR_DELAY_S.default),
        )

    def reset_session_data(self) -> None:
        reset_charge_session_data(self)

    def _init_session(
        self,
        battery_type: str,
        ah_capacity: int,
        start_stage: str,
    ) -> None:
        initialize_session(self, battery_type, ah_capacity, start_stage)

    def stop(self, clear_session: bool = True) -> None:
        stop_charge(self, clear_session=clear_session)

    def _add_phase_limits(
        self,
        actions: Dict[str, Any],
        target_v: float,
        target_i: float,
    ) -> None:
        actions["set_ovp"] = target_v + float(PROTECTION_OVP_MARGIN_V.default)
        actions["set_ocp"] = target_i + float(PROTECTION_OCP_MARGIN_A.default)
        self._phase_current_limit = target_i

    def _add_desulf_limits(
        self,
        actions: Dict[str, Any],
        target_v: float,
        target_i: float,
    ) -> None:
        actions["set_ovp"] = target_v + float(PROTECTION_OVP_MARGIN_V.default)
        actions["set_ocp"] = target_i + float(DESULFATION_OCP_MARGIN_A.default)
        self._phase_current_limit = target_i

    def _temperature_compensation_coeff(self) -> float:
        if self.battery_type == self.PROFILE_AGM:
            return float(AGM_COMPENSATION_V_PER_C.default)
        if self.battery_type == self.PROFILE_CUSTOM:
            return float(CUSTOM_COMPENSATION_V_PER_C.default)
        return float(CA_EFB_COMPENSATION_V_PER_C.default)

    def _temperature_compensation_delta(self, temp_c: Optional[float]) -> float:
        if temp_c is None or self.current_stage not in (
            self.STAGE_PREP,
            self.STAGE_MAIN,
            self.STAGE_DESULFATION,
            self.STAGE_MIX,
        ):
            return 0.0
        try:
            temp = float(temp_c)
        except (TypeError, ValueError):
            return 0.0
        raw_delta = self._temperature_compensation_coeff() * (
            float(TEMPERATURE_REFERENCE_C.default) - temp
        )
        limit = float(TEMPERATURE_MAX_DELTA_V.default)
        return max(-limit, min(limit, raw_delta))

    def _apply_temperature_compensation(
        self,
        base_v: float,
        temp_c: Optional[float],
    ) -> float:
        compensated = base_v + self._temperature_compensation_delta(temp_c)
        return clamp_pb_automatic_target_voltage(compensated)

    def _prep_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        target = select_prep_target(capacity_ah=float(self.ah_capacity))
        return (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            target.current_a,
        )

    def _main_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        if self.battery_type == self.PROFILE_CUSTOM:
            return (
                self._apply_temperature_compensation(self._custom_main_voltage, temp_c),
                min(
                    float(MAX_STAGE_CURRENT_A.default),
                    self._custom_main_current,
                ),
            )
        target = select_main_target(
            profile=self.battery_type,
            capacity_ah=float(self.ah_capacity),
            agm_stage_idx=int(self._agm_stage_idx),
        )
        current_target = target.current_a
        # A verified, session-bound MAIN Guard ceiling is monotone. After
        # physical ACK it must also constrain the controller's next tick:
        # otherwise the legacy recipe would undo the lower Iset immediately.
        guard = getattr(self, "_main_current_guard", None)
        if guard is not None and self.battery_type in (self.PROFILE_EFB, self.PROFILE_CA):
            if (guard.session_id != self._v2_trace_session_id
                    or guard.battery_id != self._v2_battery_id
                    or abs(guard.capacity_ah - self.ah_capacity) > 1e-6
                    or guard.hardware_limit_a > guard.initial_limit_a):
                from runtime.charge.strategy.main_guard_session import GuardJournalError
                raise GuardJournalError("main_guard_identity_or_ceiling_disagrees")
            current_target = min(current_target, guard.hardware_limit_a)
        return (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            current_target,
        )

    def _get_profile_target_v_i(
        self,
        temp_c: Optional[float] = None,
    ) -> Tuple[float, float]:
        if self.current_stage == self.STAGE_PREP:
            return self._prep_target(temp_c)
        if self.current_stage == self.STAGE_MAIN:
            return self._main_target(temp_c)
        if self.current_stage == self.STAGE_DESULFATION:
            return self._desulf_target(temp_c)
        if self.current_stage == self.STAGE_MIX:
            return self._mix_target(temp_c)
        if self.current_stage in {self.STAGE_SAFE_WAIT, self.STAGE_COOLING}:
            return (0.0, 0.0)
        if self.current_stage == self.STAGE_DONE:
            return self._storage_target()
        return (0.0, 0.0)

    def _get_target_v_i(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        if self._restored_target_v > 0 and self._restored_target_i > 0:
            target_v, target_i = self._restored_target_v, self._restored_target_i
        else:
            target_v, target_i = self._get_profile_target_v_i(temp_c)
        # Even an earlier remembered (restored) target cannot widen the
        # acknowledged Guard current ceiling on a continuing MAIN session.
        guard = getattr(self, "_main_current_guard", None)
        if (guard is not None and self.current_stage == self.STAGE_MAIN
                and self.battery_type in (self.PROFILE_EFB, self.PROFILE_CA)):
            if (guard.session_id != self._v2_trace_session_id
                    or guard.battery_id != self._v2_battery_id):
                from runtime.charge.strategy.main_guard_session import GuardJournalError
                raise GuardJournalError("main_guard_restored_target_identity_disagrees")
            target_i = min(target_i, guard.hardware_limit_a)
        return target_v, target_i

    def _post_charge_profile_params(self) -> Dict[str, Any]:
        return post_charge_profile_params(self.battery_type)

    def _record_safe_wait_sample(
        self,
        now: float,
        voltage: float,
        current: float,
        temp: float,
    ) -> None:
        sample_sec = int(self._post_charge_profile_params().get("sample_sec", 300))
        if now - self._last_safe_wait_sample < sample_sec:
            return
        self._safe_wait_v_samples.append((now, voltage, current, temp))
        self._last_safe_wait_sample = now

    def _make_log_event_end(
        self,
        now: float,
        ah: float,
        voltage: float,
        current: float,
        temp: float,
        trigger: str,
    ) -> Dict[str, Any]:
        return {
            "stage": self.current_stage,
            "time_sec": now - self.stage_start_time,
            "ah_on_stage": ah - self._stage_start_ah,
            "ah": ah,
            "t": temp,
            "v": voltage,
            "i": current,
            "trigger": trigger,
        }

    def _get_current_targets(
        self,
        temp_c: Optional[float] = None,
    ) -> Tuple[float, float]:
        return current_targets(self, temp_c)

    def _get_target_finish_time(self) -> Optional[float]:
        return target_finish_time(self)

    def _get_stage_max_hours(self) -> Optional[float]:
        return stage_max_hours(self)

    def _mix_current_delta_threshold(self) -> float:
        return mix_current_delta_threshold(self)

    def _exit_cc_condition(self, v_now: float) -> bool:
        return exit_cc_condition(self, v_now)

    def _exit_cv_condition(self, i_now: float) -> bool:
        return exit_cv_condition(self, i_now)

    def _session_rules_summary(self) -> str:
        return session_rules_summary(self)

    def full_reset(self) -> None:
        full_reset_charge(self)

    def _bank_fault_risk_snapshot(
        self,
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        return bank_fault_risk_snapshot(self, now, voltage, current, temp, ah)

    def get_timers(self) -> Dict[str, Any]:
        return diagnostic_timers(self)

    def get_ai_stage_snapshot(self, temp_c: Optional[float] = None) -> Dict[str, Any]:
        return ai_stage_snapshot(self, temp_c)

    def _desulf_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        """Compatibility adapter over the canonical modular DESULFATION target."""
        target = select_desulfation_target(capacity_ah=float(self.ah_capacity))
        return (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            target.current_a,
        )

    def _mix_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        """Compatibility adapter over the canonical modular MIX target."""
        target = select_mix_target(
            profile=self.battery_type,
            capacity_ah=float(self.ah_capacity),
        )
        return (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            target.current_a,
        )

    def _storage_target(self) -> Tuple[float, float]:
        target = select_storage_target()
        return target.voltage_v, target.current_a

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
        self._trace_lifecycle.reset_disagreement()
        self._main_sample_evidence.reset()
        self._recovery_safe_wait = None
        self._final_safe_wait = None

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

    def _initialize_shadow_session(self, *, started_at: Optional[float] = None) -> None:
        self._v2_session_signal_context = None
        runtime_started_at = float(
            started_at
            if started_at is not None and float(started_at) > 0
            else (self._v2_trace_started_at or self.total_start_time or time.time())
        )
        self._new_runtime(started_at=runtime_started_at)
        self._trace_lifecycle.reset_disagreement()
        self._main_sample_evidence.reset()
        try:
            target_v, _ = self._get_target_v_i()
            self._v2_target_voltage_v = float(target_v)
        except Exception:
            self._v2_target_voltage_v = None
        self._v2_last_stage = self.current_stage

    def start(self, battery_type: str, ah_capacity: int) -> None:
        if str(battery_type) == self.PROFILE_CUSTOM:
            raise RuntimeError(
                "historical Custom controller start is retired; use ProductionManualSessionManager"
            )
        self._recovery_safe_wait = None
        self._final_safe_wait = None
        start_charge(self, battery_type, ah_capacity)
        apply_trace_identity(self, new_trace_identity(self))
        self._initialize_shadow_session(started_at=self._v2_trace_started_at)

    def _clear_session_file(self) -> None:
        clear_session_file(self, session_file=SESSION_FILE)

    def _save_session(
        self, voltage: float, current: float, ah: float, *,
        terminal_request: TerminalPersistenceRequest | None = None,
    ) -> None:
        # save_session atomically writes the charge, V2 trace and optional MAIN
        # Guard journal in ONE document; no second independent rewrite here.
        save_session(
            self, voltage, current, ah, session_file=SESSION_FILE,
            terminal_request=terminal_request,
        )

    def _restore_desulfation_stage_clock(self, document: Dict[str, Any]) -> None:
        """Keep the persisted active DESULFATION clock authoritative across restart."""
        if self.current_stage != self.STAGE_DESULFATION:
            return
        try:
            saved_stage_start = float(document.get("stage_start_time"))
        except (TypeError, ValueError, OverflowError):
            return
        now = float(time.time())
        if (
            math.isfinite(saved_stage_start)
            and 0.0 < saved_stage_start <= now
            and now - saved_stage_start <= float(SESSION_START_MAX_AGE)
        ):
            self.stage_start_time = saved_stage_start

    def try_restore_session(
        self,
        voltage: float,
        current: float,
        ah: float,
    ) -> Tuple[bool, Optional[str]]:
        ok, message = restore_session(
            self,
            voltage,
            current,
            ah,
            session_file=SESSION_FILE,
        )
        if ok and self.battery_type == self.PROFILE_CUSTOM:
            logger.warning(
                "Historical Custom controller restore rejected; Manual requires operator reauthorization"
            )
            self.stop(clear_session=True)
            self._recovery_safe_wait = None
            self._final_safe_wait = None
            self._v2_runtime = None
            return (
                False,
                "Historical Custom session is retired; restart Manual with operator authorization.",
            )
        if ok:
            trace_document = dict(getattr(self, "_session_restore_document", {}))
            self._restore_desulfation_stage_clock(trace_document)
            restore_recovery_safe_wait(self, trace_document)
            restore_final_safe_wait(self, trace_document)
            self._initialize_shadow_session(started_at=self._v2_trace_started_at)
            enriched = bool(getattr(self, "_session_restore_enriched", False))
            if not enriched and not enrich_restored_session(
                self, trace_document, session_file=SESSION_FILE
            ):
                self.stop(clear_session=False)
                return False, "Restored session identity could not be durably reconciled."
        return ok, message

    @property
    def recovery_trace_context(self) -> Dict[str, Any]:
        """Stable migration read interface; identity construction belongs to evidence."""
        return build_recovery_trace_context(self).as_dict()

    def _apply_continuous_tail_hold(
        self,
        assessment: Optional[FirstStageAssessment],
        *,
        stage_before: str,
        timestamp_s: float,
    ) -> Optional[FirstStageAssessment]:
        """Default production extension point for typed first-stage evidence."""
        return assessment

    def _log_stage_transition(
        self,
        *,
        old_stage: str,
        new_stage: str,
        timestamp_s: float,
        reason: str,
    ) -> None:
        """Emit one structured transition record without changing FSM behavior."""
        if old_stage == new_stage:
            return
        owner = "modular"
        logger.info(
            "CHARGE_TRANSITION old=%s new=%s reason=%s owner=%s timestamp=%.3f",
            old_stage,
            new_stage,
            reason or "unspecified",
            owner,
            float(timestamp_s),
        )

    def _apply_recovery_safe_wait_authority(
        self,
        *,
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        actions: Dict[str, Any],
        output_is_on: Optional[Any],
    ) -> AuthorityDecision:
        continuation = self._recovery_safe_wait
        valid = (
            continuation is not None
            and self.current_stage == self.STAGE_SAFE_WAIT
            and validate_recovery_continuation(
                continuation,
                session_id=self._v2_trace_session_id,
                session_generation=self._v2_trace_started_at,
                expected_source_stage=self.STAGE_DESULFATION,
                expected_next_stage=self.STAGE_MAIN,
            )
            and continuation.recovery_attempt == int(self.antisulfate_count)
            and continuation.agm_stage_idx == int(self._agm_stage_idx)
        )
        if not valid:
            reason = "recovery_safe_wait_continuation_invalid"
            apply_stop_and_diagnose(self,
                actions=actions,
                now=now,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=reason,
            )
            self._recovery_safe_wait = None
            return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, reason)

        assert continuation is not None
        output_is_off = normalize_output_on(output_is_on) is False
        if output_is_off:
            self._record_safe_wait_sample(now, voltage, current, temp)
        decision = decide_recovery_safe_wait(
            continuation,
            now_s=now,
            voltage_v=voltage,
            output_is_off=output_is_off,
        )
        if decision.action == RecoverySafeWaitAction.WAIT:
            return AuthorityDecision(AuthorityAction.CONTINUE, decision.reason)

        actions["set_voltage"] = continuation.target_voltage_v
        actions["set_current"] = continuation.target_current_a
        self._add_phase_limits(
            actions,
            continuation.target_voltage_v,
            continuation.target_current_a,
        )
        actions["turn_on"] = True
        # The execution layer must prove the complete two-phase physical transaction
        # before this token can commit SAFE_WAIT -> MAIN.
        actions["verified_enable_transition"] = {
            "kind": "recovery_safe_wait_to_main",
            "session_id": continuation.session_id,
            "session_generation": continuation.session_generation,
            "started_at": continuation.started_at,
            "reason": decision.reason,
        }
        actions["log_event"] = "RECOVERY_SAFE_WAIT_ENABLE_ATTEMPT"
        logger.info(
            "V2 recovery SAFE_WAIT enable attempt reason=%s elapsed=%.1fs",
            decision.reason,
            decision.wait_elapsed_s,
        )
        return AuthorityDecision(
            AuthorityAction.CONTINUE,
            f"recovery_safe_wait_enable_requested:{decision.reason}",
        )

    def _apply_final_safe_wait_authority(
        self,
        *,
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        actions: Dict[str, Any],
        output_is_on: Optional[Any],
    ) -> AuthorityDecision:
        output_is_off = normalize_output_on(output_is_on) is False
        if output_is_off:
            self._record_safe_wait_sample(now, voltage, current, temp)
        effect = build_final_safe_wait_authority_effect(
            self._final_safe_wait,
            current_stage=self.current_stage,
            safe_wait_stage=self.STAGE_SAFE_WAIT,
            done_stage=self.STAGE_DONE,
            session_id=self._v2_trace_session_id,
            session_generation=self._v2_trace_started_at,
            allowed_source_stages={self.STAGE_MAIN, self.STAGE_MIX},
            now_s=now,
            voltage_v=voltage,
            output_is_off=output_is_off,
            add_phase_limits=self._add_phase_limits,
        )
        if effect is None:
            reason = "final_safe_wait_continuation_invalid"
            apply_stop_and_diagnose(self,
                actions=actions,
                now=now,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                reason=reason,
            )
            self._final_safe_wait = None
            return AuthorityDecision(AuthorityAction.STOP_AND_DIAGNOSE, reason)
        actions.update(effect.actions)
        decision = effect.decision
        if decision.action == FinalSafeWaitAction.WAIT:
            return AuthorityDecision(AuthorityAction.CONTINUE, decision.reason)
        logger.info(
            "V2 final SAFE_WAIT enable attempt reason=%s elapsed=%.1fs",
            decision.reason,
            decision.wait_elapsed_s,
        )
        return AuthorityDecision(
            AuthorityAction.CONTINUE,
            f"final_safe_wait_storage_enable_requested:{decision.reason}",
        )

    def _handle_safe_wait_stage_override(
        self,
        *,
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        actions: Dict[str, Any],
        output_is_on: Optional[Any],
    ) -> bool:
        """Compatibility hook delegating SAFE_WAIT decisions to modular owners."""

        if (
            self.battery_type == self.PROFILE_CUSTOM
            or self.current_stage != self.STAGE_SAFE_WAIT
        ):
            return False

        if self._recovery_safe_wait is not None or self._safe_wait_next_stage == self.STAGE_MAIN:
            self._apply_recovery_safe_wait_authority(
                now=now,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                actions=actions,
                output_is_on=output_is_on,
            )
            return True

        if self._final_safe_wait is not None or self._safe_wait_next_stage == self.STAGE_DONE:
            self._apply_final_safe_wait_authority(
                now=now,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                actions=actions,
                output_is_on=output_is_on,
            )
            return True

        return False

    def commit_verified_enable_transition(
        self,
        transition: Dict[str, Any],
        *,
        now: float,
        voltage: float,
        current: float,
        ah: float,
    ) -> Optional[Dict[str, str]]:
        """Commit a stage edge only after the runtime proves physical Output ON.

        Recovery-to-Main and final Storage completion use separate session-bound
        continuations. Unknown/stale tokens fail closed; the runtime must switch
        Output back OFF rather than committing an unverified controller transition.
        """
        kind = str(transition.get("kind") or "")
        if kind == "final_safe_wait_to_done":
            effect = build_final_safe_wait_completion_effect(
                FinalSafeWaitCompletionInput(
                    continuation=self._final_safe_wait,
                    current_stage=self.current_stage,
                    safe_wait_stage=self.STAGE_SAFE_WAIT,
                    done_stage=self.STAGE_DONE,
                    active_session_generation=self._v2_trace_started_at,
                    transition=transition,
                    now_s=now,
                    voltage_v=voltage,
                    current_a=current,
                    ah=ah,
                )
            )
            if effect is None:
                logger.error("verified final completion rejected: no matching SAFE_WAIT continuation")
                return None
            return apply_final_safe_wait_completion_effect(self, effect)
        if kind != "recovery_safe_wait_to_main":
            return None
        continuation = self._recovery_safe_wait
        if continuation is None or self.current_stage != self.STAGE_SAFE_WAIT:
            logger.error("verified recovery resume rejected: no matching SAFE_WAIT continuation")
            return None
        token_session = str(transition.get("session_id") or "") or None
        try:
            token_started_at = float(transition.get("started_at"))
            token_session_generation = float(transition.get("session_generation"))
        except (TypeError, ValueError):
            return None
        if (
            token_session != continuation.session_id
            or continuation.session_generation is None
            or not math.isfinite(token_started_at)
            or not math.isfinite(token_session_generation)
            or abs(token_started_at - continuation.started_at) > 1e-6
            or abs(token_session_generation - float(continuation.session_generation)) > 1e-6
            or abs(token_session_generation - float(self._v2_trace_started_at)) > 1e-6
        ):
            logger.error("verified recovery resume rejected: continuation token mismatch")
            return None

        prev = self.current_stage
        self.current_stage = continuation.next_stage
        self._clear_restored_targets()
        self.stage_start_time = float(now)
        self._stage_start_ah = float(ah)
        self._blanking_until = float(now) + float(STAGE_TRANSITION_BLANKING_S.default)
        self.v_max_recorded = None
        self.i_min_recorded = None
        self._delta_trigger_count = 0
        self._main_sample_evidence.reset()
        self._safe_wait_next_stage = None
        self._safe_wait_target_v = 0.0
        self._safe_wait_target_i = 0.0
        self._safe_wait_start = 0.0
        self._recovery_safe_wait = None
        reason = str(transition.get("reason") or "verified_enable")
        self._log_stage_transition(
            old_stage=prev,
            new_stage=self.current_stage,
            timestamp_s=float(now),
            reason=f"recovery_safe_wait_verified_enable:{reason}",
        )
        self._save_session(float(voltage), float(current), float(ah))
        logger.info(
            "V2 recovery SAFE_WAIT -> %s committed after verified Output ON reason=%s",
            self.current_stage,
            reason,
        )
        if reason == "timeout":
            return {
                "log_event": "START | RECOVERY_SAFE_WAIT_TIMEOUT_TO_MAIN",
                "notify": (
                    "?? ?????????? ?????? ???????? ????? ?????????? ?????. "
                    f"????? ????????????? ???????? ??????????? ??????? ? Main "
                    f"({continuation.target_voltage_v:.1f}?)."
                ),
            }
        return {
            "log_event": "START | RECOVERY_SAFE_WAIT_TO_MAIN",
            "notify": "<b>?? ??????? ? Main Charge ???????????.</b> Output ??????? ? ??????? ?????????.",
        }

    def _handle_mix_stage_override(
        self,
        *,
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        actions: Dict[str, Any],
        output_is_on: Optional[Any],
        is_cv: bool,
        is_cc: Optional[bool],
    ) -> bool:
        """Compatibility hook marking MIX as modular-authoritative.

        The production MIX path now bypasses historical ``ChargeController.tick()``
        entirely; this hook remains only for direct characterization callers.
        """
        return bool(
            self.battery_type != self.PROFILE_CUSTOM
            and self.current_stage == self.STAGE_MIX
        )

    def _is_authoritative_stage(self, stage: str) -> bool:
        return (
            self.battery_type != self.PROFILE_CUSTOM
            and (
                stage in {self.STAGE_MAIN, self.STAGE_DESULFATION, self.STAGE_MIX}
                or (
                    stage == self.STAGE_SAFE_WAIT
                    and (
                        self._recovery_safe_wait is not None
                        or self._final_safe_wait is not None
                        or self._safe_wait_next_stage == self.STAGE_MAIN
                        or self._safe_wait_next_stage == self.STAGE_DONE
                    )
                )
            )
        )

    async def _run_stage_scaffold_tick(
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
        manual_active: bool,
    ) -> Dict[str, Any]:
        """Route migrated production stages around historical ChargeController.tick.

        MAIN, intermediate recovery, MIX, and final SAFE_WAIT use modular runtime
        scaffolds. Historical Custom is retired from production entirely: an IDLE
        residue is inert, while any active residue fails closed to Output OFF.
        Other not-yet-migrated automatic stages retain the compatibility path.
        """
        if self.battery_type == self.PROFILE_CUSTOM:
            if stage_before == self.STAGE_IDLE:
                return {}
            logger.error(
                "Active historical Custom controller state rejected stage=%s; forcing OFF",
                stage_before,
            )
            self.stop(clear_session=True)
            return {
                "turn_off": True,
                "log_event": "HISTORICAL_CUSTOM_RUNTIME_RETIRED",
                "notify": (
                    "❌ Исторический Custom-контроллер отключён. "
                    "Ручной режим запускается только через Manual."
                ),
            }

        if stage_before in {
            self.STAGE_PREP,
            self.STAGE_COOLING,
            self.STAGE_IDLE,
            self.STAGE_DONE,
        }:
            return await run_authoritative_residual_scaffold(
                self,
                stage_before=stage_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                ah=ah,
                output_is_on=output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
                manual_active=manual_active,
                now_s=time.time(),
            )

        if (
            self.battery_type != self.PROFILE_CUSTOM
            and stage_before == self.STAGE_MAIN
        ):
            return await run_authoritative_main_scaffold(
                self,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                ah=ah,
                output_is_on=output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
                manual_active=manual_active,
                now_s=time.time(),
            )

        recovery_safe_wait = (
            stage_before == self.STAGE_SAFE_WAIT
            and (
                self._recovery_safe_wait is not None
                or self._safe_wait_next_stage == self.STAGE_MAIN
            )
        )
        if (
            self.battery_type != self.PROFILE_CUSTOM
            and (stage_before == self.STAGE_DESULFATION or recovery_safe_wait)
        ):
            return await run_authoritative_recovery_scaffold(
                self,
                stage_before=stage_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                ah=ah,
                output_is_on=output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
                manual_active=manual_active,
                now_s=time.time(),
            )

        final_safe_wait = (
            stage_before == self.STAGE_SAFE_WAIT
            and (
                self._final_safe_wait is not None
                or self._safe_wait_next_stage == self.STAGE_DONE
            )
        )
        if (
            self.battery_type != self.PROFILE_CUSTOM
            and (stage_before == self.STAGE_MIX or final_safe_wait)
        ):
            return await run_authoritative_mix_scaffold(
                self,
                stage_before=stage_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                ah=ah,
                output_is_on=output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
                manual_active=manual_active,
                report_limit_s=(
                    self._mix_limit_seconds()
                    if stage_before == self.STAGE_MIX
                    else safe_wait_max_seconds()
                ),
                now_s=time.time(),
            )

        reason = f"unsupported_modular_stage:{stage_before}"
        logger.error(
            "Unsupported modular stage; rejecting stage=%s profile=%s",
            stage_before,
            self.battery_type,
        )
        self.stop(clear_session=True)
        return {
            "turn_off": True,
            "log_event": "HISTORICAL_STAGE_RUNTIME_RETIRED",
            "notify": (
                "❌ Этап не принадлежит модульному runtime. "
                "Заряд остановлен до повторной авторизации."
            ),
            "recovery_shadow": {
                "status": "fail_closed",
                "reason": reason,
                "authority": "v2",
            },
        }

    def _mix_limit_seconds(self) -> float:
        """Compatibility accessor over the canonical modular MIX authority limit."""
        return mix_max_active_seconds(self.battery_type)

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
        output_is_on: Optional[Any] = None,
    ) -> Optional[AuthorityDecision]:
        if not self._is_authoritative_stage(stage_before) or self.current_stage != stage_before:
            return None

        if stage_before == self.STAGE_DESULFATION:
            decision = decide_desulfation(
                active_elapsed_s=max(
                    0.0,
                    float(timestamp_s) - float(self.stage_start_time),
                )
            )
            if decision.action == DesulfationAction.COMPLETE_TO_SAFE_WAIT:
                target_v, target_i = self._main_target(temp)
                if not complete_desulfation_to_safe_wait(
                    self, main_target_voltage_v=target_v,
                    main_target_current_a=target_i, now_s=timestamp_s, ah=ah,
                    voltage_v=voltage, measured_current_a=current,
                    temperature_c=temp, actions=actions,
                ):
                    return AuthorityDecision(
                        AuthorityAction.CONTINUE,
                        "desulfation_completion_session_identity_invalid",
                    )
                return AuthorityDecision(
                    AuthorityAction.COMPLETE_TO_SAFE_WAIT,
                    decision.reason,
                )
            return AuthorityDecision(AuthorityAction.CONTINUE, decision.reason)

        if (
            stage_before == self.STAGE_SAFE_WAIT
            and (
                self._recovery_safe_wait is not None
                or self._safe_wait_next_stage == self.STAGE_MAIN
            )
        ):
            return self._apply_recovery_safe_wait_authority(
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                actions=actions,
                output_is_on=output_is_on,
            )

        if (
            stage_before == self.STAGE_SAFE_WAIT
            and (
                self._final_safe_wait is not None
                or self._safe_wait_next_stage == self.STAGE_DONE
            )
        ):
            return self._apply_final_safe_wait_authority(
                now=timestamp_s,
                voltage=voltage,
                current=current,
                temp=temp,
                ah=ah,
                actions=actions,
                output_is_on=output_is_on,
            )

        if stage_before != self.STAGE_MAIN and stage_before != self.STAGE_MIX:
            return None

        if stage_before == self.STAGE_MAIN:
            return apply_main_authority_tick(
                self, record=record, first_stage=first_stage,
                timestamp_s=timestamp_s, voltage=voltage, current=current,
                temp=temp, ah=ah, is_cv=is_cv, actions=actions,
            )

        return apply_mix_authority_tick(
            self,
            record=record,
            timestamp_s=timestamp_s,
            voltage=voltage,
            current=current,
            temp=temp,
            ah=ah,
            is_cv=is_cv,
            is_cc=is_cc,
            actions=actions,
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
        manual_active: bool = False,
    ) -> Dict[str, Any]:
        stage_before = self.current_stage
        target_before = self._v2_target_voltage_v
        if target_before is None and stage_before not in {self.STAGE_IDLE, self.STAGE_SAFE_WAIT, self.STAGE_COOLING}:
            try:
                target_before = float(self._get_target_v_i(temp_ext)[0])
            except Exception:
                target_before = None

        # Persistent Manual-OFF is an asynchronous terminal kill condition
        # owned outside AUTO chemistry. Its armed state must never alter automatic
        # stage decisions before the external condition actually fires.
        actions = await self._run_stage_scaffold_tick(
            stage_before=stage_before,
            voltage=voltage,
            current=current,
            temp_ext=temp_ext,
            is_cv=is_cv,
            ah=ah,
            output_is_on=output_is_on,
            manual_off_active=False,
            is_cc=is_cc,
            manual_active=manual_active,
        )

        timestamp_s = self.last_update_time or time.time()
        resolved_is_cc = bool(is_cc) if is_cc is not None else not bool(is_cv)
        authority_decision: Optional[AuthorityDecision] = None
        first_stage: Optional[FirstStageAssessment] = None
        record = None

        try:
            runtime = self._v2_runtime
            if runtime is None:
                runtime = self._new_runtime(
                    started_at=self._v2_trace_started_at or self.total_start_time or timestamp_s
                )
            record = runtime.observe(
                RecoveryTracePoint(
                    timestamp_s=timestamp_s,
                    stage=stage_before,
                    voltage_v=finite_or_nan(voltage),
                    current_a=finite_or_nan(current),
                    temp_c=finite_or_nan(temp_ext),
                    is_cv=bool(is_cv),
                    is_cc=resolved_is_cc,
                    target_voltage_v=target_before,
                    ah=finite_or_nan(ah),
                ),
                legacy_actions=actions,
                output_is_on=normalize_output_on(output_is_on),
            )

            metrics = record.analysis.metrics
            if SignalEvent.CURRENT_MINIMUM_UPDATED in record.analysis.events:
                logger.info(
                    "CURRENT_MINIMUM_UPDATED Imin=%.3fA stage=%s session=%s",
                    metrics.current_min_a if metrics.current_min_a is not None else float("nan"),
                    stage_before,
                    self._v2_trace_session_id or "-",
                )
            if SignalEvent.VOLTAGE_MAXIMUM_UPDATED in record.analysis.events:
                logger.info(
                    "CHARGE_EVIDENCE kind=maximum event=update mode=CC Vmax=%.3f timestamp=%.3f",
                    metrics.voltage_max_v if metrics.voltage_max_v is not None else float("nan"),
                    timestamp_s,
                )
            if SignalEvent.CURRENT_REVERSAL_CONFIRMED in record.analysis.events:
                logger.info(
                    "CHARGE_EVIDENCE kind=delta event=confirmation mode=CV Imin=%.3f delta=%.3f timestamp=%.3f",
                    metrics.current_min_a if metrics.current_min_a is not None else float("nan"),
                    metrics.delta_current_from_min_a if metrics.delta_current_from_min_a is not None else float("nan"),
                    timestamp_s,
                )
            if SignalEvent.VOLTAGE_REVERSAL_CONFIRMED in record.analysis.events:
                logger.info(
                    "CHARGE_EVIDENCE kind=delta event=confirmation mode=CC Vmax=%.3f delta=%.3f timestamp=%.3f",
                    metrics.voltage_max_v if metrics.voltage_max_v is not None else float("nan"),
                    metrics.delta_voltage_from_max_v if metrics.delta_voltage_from_max_v is not None else float("nan"),
                    timestamp_s,
                )
            analyzer = getattr(getattr(runtime, "tracker", None), "_analyzer", None)
            mode = "CV" if bool(is_cv) else ("CC" if bool(resolved_is_cc) else None)
            self._v2_session_signal_context = build_signal_context(SignalContextInput(
                stage=stage_before,
                mode=mode,
                session_id=self._v2_trace_session_id,
                session_generation=float(self._v2_trace_started_at or 0.0),
                output_is_on=output_is_on,
                is_cv=bool(is_cv),
                is_cc=bool(resolved_is_cc),
                telemetry_valid=not record.analysis.has(SignalEvent.TELEMETRY_INVALID),
                timestamp_s=float(timestamp_s),
                now_s=time.time(),
                target_voltage_v=target_before,
                metrics=metrics,
                analyzer=analyzer,
            ))

            metrics = record.analysis.metrics
            sample = MainSampleEvidenceInput(
                stage=stage_before,
                main_stage=self.STAGE_MAIN,
                target_voltage_v=target_before,
                timestamp_s=float(timestamp_s),
                voltage_v=float(voltage),
                current_a=float(current),
                is_cv=bool(is_cv),
                chemistry=chemistry_for_profile(self.battery_type),
                capacity_ah=float(self.ah_capacity),
                plateau_required_minutes=(
                    float(AGM_PLATEAU_REQUIRED_MINUTES.default)
                    if self.battery_type == self.PROFILE_AGM
                    else float(STANDARD_PLATEAU_REQUIRED_MINUTES.default)
                ),
                plateau_window_minutes=float(PLATEAU_EVIDENCE_WINDOW_MINUTES.default),
                events=frozenset(record.analysis.events),
                dtemp_c_per_min=metrics.d_temp_c_per_min,
                dcurrent_a_per_min=metrics.d_current_a_per_min,
                dvoltage_v_per_min=metrics.d_voltage_v_per_min,
                temperature_c=getattr(getattr(record.analysis, "sample", None), "temp_c", None),
            )
            first_stage_evidence = self._main_sample_evidence.assess(sample)
            first_stage = self._apply_continuous_tail_hold(
                first_stage_evidence.assessment,
                stage_before=stage_before,
                timestamp_s=float(timestamp_s),
            )

            if self._is_authoritative_stage(stage_before):
                if temp_ext is None:
                    temp_value = math.nan
                else:
                    temp_value = finite_or_nan(temp_ext)
                if math.isfinite(temp_value):
                    authority_decision = self._apply_authoritative_decision(
                        record=record,
                        first_stage=first_stage,
                        stage_before=stage_before,
                        timestamp_s=timestamp_s,
                        voltage=float(voltage),
                        current=float(current),
                        temp=temp_value,
                        ah=float(ah),
                        is_cv=bool(is_cv),
                        is_cc=resolved_is_cc,
                        actions=actions,
                        output_is_on=output_is_on,
                    )
            else:
                # Residual PREP/COOLING/IDLE/DONE stages are modular-owned too;
                # no historical transition source remains to audit.
                self._trace_lifecycle.observe_disagreement(record, stage=stage_before)

            trace_point = build_trace_point_metadata(TracePointInput(
                timestamp_s=timestamp_s,
                stage_before=stage_before,
                stage_after=self.current_stage,
                target_before=target_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                is_cc=resolved_is_cc,
                ah=ah,
                output_is_on=output_is_on,
            ))
            actions["recovery_shadow"] = build_shadow_metadata(
                record,
                trace_point=trace_point,
                first_stage=first_stage,
                authority_decision=authority_decision,
            )
        except Exception as exc:
            # A failed modular evidence path must fail closed; there is no fallback
            # transition owner to receive control after an internal error.
            logger.exception("Recovery observation/authority failed")
            self._v2_session_signal_context = None
            trace_point = build_trace_point_metadata(TracePointInput(
                timestamp_s=timestamp_s,
                stage_before=stage_before,
                stage_after=self.current_stage,
                target_before=target_before,
                voltage=voltage,
                current=current,
                temp_ext=temp_ext,
                is_cv=is_cv,
                is_cc=resolved_is_cc,
                ah=ah,
                output_is_on=output_is_on,
            ))
            actions["recovery_shadow"] = {
                "status": "error",
                "decision": None,
                "reason": "V2 observation/authority failed",
                "error_type": type(exc).__name__,
                "authority": "modular",
                "trace_point": trace_point,
            }
            if self._is_authoritative_stage(stage_before) and self.current_stage == stage_before:
                temp_value = finite_or_nan(temp_ext)
                if math.isfinite(temp_value):
                    apply_stop_and_diagnose(self,
                        actions=actions,
                        now=timestamp_s,
                        voltage=finite_or_nan(voltage),
                        current=finite_or_nan(current),
                        temp=temp_value,
                        ah=finite_or_nan(ah),
                        reason=f"v2_internal_error:{type(exc).__name__}",
                    )
                else:
                    actions["emergency_stop"] = True
                    actions["turn_off"] = True

        try:
            if await self._trace_lifecycle.capture_if_ready(
                build_recovery_trace_context(self), actions["recovery_shadow"],
                idle_stage=self.STAGE_IDLE,
            ):
                actions["recovery_shadow"]["persistence"] = "stored"
        except Exception as exc:
            logger.exception("RECOVERY_TRACE persistence failed; actuator decision remains valid")
            actions["recovery_shadow"]["persistence"] = "error"
            actions["recovery_shadow"]["persistence_error_type"] = type(exc).__name__

        next_target = actions.get("set_voltage")
        if next_target is not None:
            self._v2_target_voltage_v = finite_or_nan(next_target)
        elif self.current_stage != stage_before:
            try:
                self._v2_target_voltage_v = float(self._get_target_v_i(temp_ext)[0])
            except Exception:
                self._v2_target_voltage_v = None
        self._v2_last_stage = self.current_stage

        transition_reason = ""
        if authority_decision is not None:
            transition_reason = str(authority_decision.reason or "")
        if not transition_reason:
            transition_reason = str(actions.get("log_event") or actions.get("log_event_end") or "")
        self._log_stage_transition(
            old_stage=stage_before,
            new_stage=self.current_stage,
            timestamp_s=timestamp_s,
            reason=transition_reason,
        )

        # Mix scaffold temporarily hid the true stage clock from legacy persistence.
        # Rewrite the durable session after restoring/applying the authoritative state.
        if self.current_stage not in {self.STAGE_IDLE, self.STAGE_DONE}:
            self._save_session(float(voltage), float(current), float(ah))

        return actions

    def ui_support_snapshot(self) -> Dict[str, Any]:
        """Compact mode-specific status for Telegram/UI without exposing raw internals."""
        metrics: Dict[str, Any] = {}
        decision = None
        reason = None
        events = []
        raw_finish_evidence = getattr(self, "_finish_evidence", None)
        finish_evidence = None
        if isinstance(raw_finish_evidence, dict):
            finish_evidence = {
                "mode": raw_finish_evidence.get("mode"),
                "reference_value": raw_finish_evidence.get("reference_value"),
                "accepted_delta": raw_finish_evidence.get("accepted_delta"),
                "accepted_at": raw_finish_evidence.get("accepted_at"),
                "available": True,
            }
        if self._v2_runtime is not None and self._v2_runtime.records:
            last = self._v2_runtime.records[-1]
            m = last.analysis.metrics
            current_min_started_at = None
            sample_timestamp = getattr(last.analysis.sample, "timestamp_s", None)
            seconds_since_current_min = m.seconds_since_current_min
            if sample_timestamp is not None and seconds_since_current_min is not None:
                current_min_started_at = float(sample_timestamp) - float(seconds_since_current_min)
            decision = last.decision.decision.value
            reason = last.decision.reason
            events = sorted(event.value for event in last.analysis.events)
            metrics = {
                "d_voltage_v_per_min": m.d_voltage_v_per_min,
                "d_current_a_per_min": m.d_current_a_per_min,
                "d_temp_c_per_min": m.d_temp_c_per_min,
                "current_min_a": m.current_min_a,
                "seconds_since_current_min": seconds_since_current_min,
                "current_min_started_at": current_min_started_at,
                "delta_current_from_min_a": m.delta_current_from_min_a,
                "reversal_threshold_a": m.reversal_threshold_a,
                "voltage_max_v": m.voltage_max_v,
                "seconds_since_voltage_max": m.seconds_since_voltage_max,
                "delta_voltage_from_max_v": m.delta_voltage_from_max_v,
                "voltage_reversal_threshold_v": m.voltage_reversal_threshold_v,
            }
        runtime_analysis_available = bool(
            self._v2_runtime is not None and self._v2_runtime.records
        )
        # A record alone is not proof that the current extrema decision is
        # usable.  Neutral/off and invalid samples are deliberately recorded
        # for diagnostics, but must not authorize an operator-facing extrema
        # claim after restore or an output transition.
        runtime_evidence_available = False
        context = self._v2_session_signal_context
        if runtime_analysis_available and isinstance(context, dict):
            expected_mode = "CV" if self.is_cv else ("CC" if self.is_cc else None)
            last = self._v2_runtime.records[-1]
            runtime_evidence_available = (
                context.get("mode") == expected_mode
                and context.get("output_on") is True
                and context.get("telemetry_valid") is True
                and not last.analysis.has(SignalEvent.TELEMETRY_INVALID)
            )
        return {
            "authoritative": True,
            "battery_id": self._v2_battery_id,
            "intent": self._v2_intent.value,
            "condition": self._v2_condition_before.value,
            "stage": self.current_stage,
            "is_cv": bool(self.is_cv),
            "is_cc": bool(self.is_cc),
            "finish_hold_started_at": self.finish_timer_start,
            "delta_reported": bool(getattr(self, "_delta_reported", False)),
            "finish_evidence": finish_evidence,
            "runtime_analysis_available": runtime_analysis_available,
            "runtime_evidence_available": runtime_evidence_available,
            "decision": decision,
            "reason": reason,
            "events": events,
            "metrics": metrics,
        }

    def signal_analyzer_diagnostic_snapshot(self) -> Dict[str, Any]:
        """Return a read-only, non-authoritative analyzer diagnostic snapshot.

        This deliberately exposes observation state only.  It is not consumed by
        the controller, safety gates, persistence, or operator HMI decisions.
        """
        context = self._v2_session_signal_context
        runtime = self._v2_runtime
        analyzer = getattr(getattr(runtime, "tracker", None), "_analyzer", None)
        records = getattr(runtime, "records", None) if runtime is not None else None
        last_record = records[-1] if records else None
        if analyzer is None or not isinstance(context, dict):
            return {
                "available": False,
                "session_id": context.get("session_id") if isinstance(context, dict) else self._v2_trace_session_id,
                "mode": context.get("mode") if isinstance(context, dict) else None,
                "runtime_evidence_available": False,
                "cc": {"voltage_max_v": None, "voltage_max_time": None,
                       "delta_reference_v": None, "voltage_reversal_confirmations": 0,
                       "voltage_reversal_emitted": False},
                "cv": {"current_min_a": None, "current_min_time": None,
                       "delta_reference_a": None, "current_reversal_confirmations": 0,
                       "current_reversal_emitted": False},
                "last_sample": None,
            }

        point = last_record.point if last_record is not None else None
        invalid = bool(last_record and last_record.analysis.has(SignalEvent.TELEMETRY_INVALID))
        output_on = context.get("output_on")
        accepted = bool(last_record is not None and not invalid and output_on is not False)
        reject_reason = None
        if invalid:
            reject_reason = "telemetry_invalid"
        elif last_record is not None and output_on is False:
            reject_reason = "output_off_gate"
        elif last_record is None:
            reject_reason = "no_runtime_sample"

        last_sample = None
        if point is not None:
            last_sample = {
                "timestamp": point.timestamp_s,
                "voltage": point.voltage_v,
                "current": point.current_a,
                "is_cv": point.is_cv,
                "is_cc": point.is_cc,
                "output_on": output_on,
                "telemetry_valid": not invalid,
                "accepted": accepted,
                "reject_reason": reject_reason,
            }
        snapshot = self.ui_support_snapshot()
        return {
            "available": True,
            "session_id": context.get("session_id"),
            "mode": context.get("mode"),
            "runtime_evidence_available": bool(snapshot.get("runtime_evidence_available")),
            "cc": {
                "voltage_max_v": analyzer._voltage_max_v,
                "voltage_max_time": analyzer._voltage_max_time_s,
                "delta_reference_v": analyzer._voltage_max_v,
                "voltage_reversal_confirmations": analyzer._voltage_reversal_confirmations,
                "voltage_reversal_emitted": bool(analyzer._voltage_reversal_emitted),
            },
            "cv": {
                "current_min_a": analyzer._current_min_a,
                "current_min_time": analyzer._current_min_time_s,
                "delta_reference_a": analyzer._current_min_a,
                "current_reversal_confirmations": analyzer._reversal_confirmations,
                "current_reversal_emitted": bool(analyzer._reversal_emitted),
            },
            "last_sample": last_sample,
        }

    @property
    def recovery_shadow_summary(self) -> Dict[str, Any]:
        if self._v2_runtime is None:
            return {
                "samples": 0,
                "decision_counts": {},
                "disagreement_counts": {},
                "last_disagreement": None,
                "last_disagreement_repeats": 0,
                "authoritative": True,
            }
        summary = dict(self._v2_runtime.summary())
        summary["last_disagreement"] = self._trace_lifecycle.last_disagreement
        summary["last_disagreement_repeats"] = self._trace_lifecycle.disagreement_repeat_count
        summary["authoritative"] = True
        return summary
