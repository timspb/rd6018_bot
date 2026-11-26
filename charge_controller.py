from __future__ import annotations

import json
import logging
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
    shift_active_clocks as shift_controller_active_clocks,
)
from runtime.charge.sample_state import mark_stage_sample
from runtime.charge.host_configuration import ManagedChargeHostConfiguration
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

SESSION_START_MAX_AGE = SESSION_START_MAX_AGE_S
from runtime.charge.evidence.first_stage import (
    FirstStageAssessment,
    FirstStageState,
    MainSampleEvidenceEvaluator,
)
from runtime.charge.evidence.trace_context import (
    TraceLifecycle,
    recovery_trace_context as build_recovery_trace_context,
)
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision
from recovery_shadow import ShadowRecoveryRuntime
from signal_analyzer import SignalEvent
from runtime.charge.diagnostics import (
    ui_support_snapshot,
    signal_analyzer_diagnostic_snapshot,
    get_timers as diagnostic_timers,
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
from runtime.charge.runtime.final_safe_wait_completion import (
    FinalSafeWaitCompletionInput,
    apply_final_safe_wait_completion_effect,
    build_final_safe_wait_completion_effect,
)
from runtime.charge.runtime.recovery_safe_wait_completion import (
    RecoverySafeWaitCompletionInput,
    apply_recovery_safe_wait_completion_effect,
    build_recovery_safe_wait_completion_effect,
)
from runtime.charge.strategy.desulfation import select_desulfation_target
from runtime.charge.strategy.desulfation_variables import (
    desulfation_duration_seconds,
)
from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitContinuation,
    validate_final_continuation,
)
from runtime.charge.strategy.main_targets import select_main_target
from application.production_target_policy import bound_host_target, is_production_host
from runtime.charge.strategy.prep import select_prep_target
from runtime.charge.strategy.mix import select_mix_target
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitContinuation,
    validate_recovery_continuation,
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
        host_configuration: Optional[ManagedChargeHostConfiguration] = None,
    ) -> None:
        self.host_configuration = host_configuration or ManagedChargeHostConfiguration()
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
        if self.host_configuration.production_extensions_enabled:
            from application.production_session_extensions import initialize_production_session_state
            from runtime.charge.diagnostics import initialize_battery_fault_state
            initialize_production_session_state(self)
            initialize_battery_fault_state(self)

    @property
    def current_stage(self) -> str:
        return getattr(self, "_current_stage", self.STAGE_IDLE)

    @current_stage.setter
    def current_stage(self, value: str) -> None:
        set_current_stage(self, value)

    @property
    def is_active(self) -> bool:
        return self.current_stage not in (self.STAGE_IDLE, self.STAGE_DONE)

    def shift_active_clocks(self, seconds: float) -> None:
        """Compatibility wrapper for controller-state clock shifting."""
        shift_controller_active_clocks(self, seconds)

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
        *,
        now_s: float | None = None,
        clear_session: bool = True,
    ) -> None:
        initialize_session(
            self, battery_type, ah_capacity, start_stage,
            now_s=now_s, clear_session=clear_session,
        )

    def stop(self, clear_session: bool = True) -> None:
        stop_charge(self, clear_session=clear_session)

    def _add_phase_limits(
        self,
        actions: Dict[str, Any],
        target_v: float,
        target_i: float,
    ) -> None:
        # Charge stages own working V/I targets; independent guards enforce
        # measured envelopes, temperature, Output state and lease.
        self._phase_current_limit = target_i

    def _add_desulf_limits(
        self,
        actions: Dict[str, Any],
        target_v: float,
        target_i: float,
    ) -> None:
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
        result = (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            target.current_a,
        )
        return bound_host_target(self, result, hv=False)

    def _main_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        if self.battery_type == self.PROFILE_CUSTOM:
            return bound_host_target(self, (
                self._apply_temperature_compensation(self._custom_main_voltage, temp_c),
                min(
                    float(MAX_STAGE_CURRENT_A.default),
                    self._custom_main_current,
                ),
            ), hv=False)
        from runtime.charge.programs.native_recipe_session import native_target_parameters
        target = select_main_target(
            profile=self.battery_type,
            capacity_ah=float(self.ah_capacity),
            agm_stage_idx=int(self._agm_stage_idx),
            **native_target_parameters(self, "MAIN"),
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
        result = (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            current_target,
        )
        return bound_host_target(self, result, hv=False)

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
        return bound_host_target(
            self, (target_v, target_i),
            hv=self.current_stage in {self.STAGE_DESULFATION, self.STAGE_MIX},
        )

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
        from application.production_session_extensions import auto_stage_max_hours
        return auto_stage_max_hours(self, stage_max_hours(self))

    def _mix_current_delta_threshold(self) -> float:
        return mix_current_delta_threshold(self)

    def _exit_cc_condition(self, v_now: float) -> bool:
        return exit_cc_condition(self, v_now)

    def _exit_cv_condition(self, i_now: float) -> bool:
        return exit_cv_condition(self, i_now)

    def _session_rules_summary(self) -> str:
        from application.production_session_extensions import auto_session_rules_summary
        return auto_session_rules_summary(self, session_rules_summary(self))

    def full_reset(self) -> None:
        full_reset_charge(self)

    def get_timers(self) -> Dict[str, Any]:
        from application.production_session_extensions import auto_timers
        return auto_timers(self, diagnostic_timers(self))

    def get_ai_stage_snapshot(self, temp_c: Optional[float] = None) -> Dict[str, Any]:
        from integrations.ai.snapshot import get_ai_stage_snapshot
        return get_ai_stage_snapshot(self, temp_c)

    def _desulf_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        """Compatibility adapter over the canonical modular DESULFATION target."""
        from runtime.charge.programs.native_recipe_session import native_target_parameters
        params = native_target_parameters(self, "DESULFATION")
        target = select_desulfation_target(
            capacity_ah=float(self.ah_capacity),
            **{key: value for key, value in params.items() if key != "duration_hours"},
        )
        result = (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            target.current_a,
        )
        return bound_host_target(self, result, hv=True)

    def _mix_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        """Compatibility adapter over the canonical modular MIX target."""
        from runtime.charge.programs.native_recipe_session import native_target_parameters
        target = select_mix_target(
            profile=self.battery_type,
            capacity_ah=float(self.ah_capacity),
            **native_target_parameters(self, "MIX"),
        )
        result = (
            self._apply_temperature_compensation(target.voltage_v, temp_c),
            target.current_a,
        )
        return bound_host_target(self, result, hv=True)

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
        if is_production_host(self):
            from application.production_runtime_policy import new_production_runtime
            return new_production_runtime(self, started_at=started_at)
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

    def start(
        self, battery_type: str, ah_capacity: int, *,
        now_s: float | None = None, clear_session: bool = True,
        trace_identity: Any = None,
    ) -> None:
        if str(battery_type) == self.PROFILE_CUSTOM:
            raise RuntimeError(
                "historical Custom controller start is retired; use ProductionManualSessionManager"
            )
        self._recovery_safe_wait = None
        self._final_safe_wait = None
        start_charge(
            self, battery_type, ah_capacity,
            now_s=now_s, clear_session=clear_session,
        )
        identity = trace_identity if trace_identity is not None else new_trace_identity(self, now=now_s)
        apply_trace_identity(self, identity)
        self._initialize_shadow_session(started_at=self._v2_trace_started_at)

    def _clear_session_file(self) -> None:
        clear_session_file(self, session_file=SESSION_FILE)

    def _save_session(
        self, voltage: float, current: float, ah: float, *,
        terminal_request: TerminalPersistenceRequest | None = None,
        restore_expected_bytes: bytes | None = None,
    ):
        # save_session atomically writes the charge, V2 trace and optional MAIN
        # Guard journal in ONE document; no second independent rewrite here.
        return save_session(
            self, voltage, current, ah, session_file=SESSION_FILE,
            terminal_request=terminal_request,
            restore_expected_bytes=restore_expected_bytes,
        )

    def _restore_desulfation_stage_clock(self, document: Dict[str, Any]) -> None:
        """Compatibility delegate for the existing restore continuation owner."""
        from runtime.charge.session_continuation_restore import restore_desulfation_stage_clock

        restore_desulfation_stage_clock(
            self, document, max_session_age_s=SESSION_START_MAX_AGE,
        )

    def try_restore_session(
        self,
        voltage: float,
        current: float,
        ah: float,
        output_is_on: Optional[Any] = None,
        is_cv: Optional[bool] = None,
        is_cc: Optional[bool] = None,
        _guarded_activation_permit: Any = None,
    ) -> Tuple[bool, Optional[str]]:
        from runtime.charge.session_continuation_restore import restore_controller_session

        return restore_controller_session(
            self, voltage, current, ah,
            output_is_on=output_is_on, is_cv=is_cv, is_cc=is_cc,
            guarded_activation_permit=_guarded_activation_permit,
            session_file=SESSION_FILE, persist_restore=restore_session,
            enrich_restored_session=enrich_restored_session,
            custom_profile=self.PROFILE_CUSTOM,
            max_session_age_s=SESSION_START_MAX_AGE,
        )

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
        effect = build_recovery_safe_wait_completion_effect(
            RecoverySafeWaitCompletionInput(
                continuation=self._recovery_safe_wait,
                current_stage=self.current_stage,
                safe_wait_stage=self.STAGE_SAFE_WAIT,
                active_session_generation=self._v2_trace_started_at,
                transition=transition,
                now_s=now,
                voltage_v=voltage,
                current_a=current,
                ah=ah,
            )
        )
        if effect is None:
            logger.error("verified recovery resume rejected: no matching SAFE_WAIT continuation")
            return None
        return apply_recovery_safe_wait_completion_effect(self, effect)

    def ui_support_snapshot(self) -> Dict[str, Any]:
        return ui_support_snapshot(self)

    def signal_analyzer_diagnostic_snapshot(self) -> Dict[str, Any]:
        """Return a non-authoritative analyzer diagnostic snapshot.

        This read-only compatibility façade never grants charge or safety authority.
        """
        return signal_analyzer_diagnostic_snapshot(self)

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
