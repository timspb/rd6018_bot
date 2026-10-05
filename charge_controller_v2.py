from __future__ import annotations

import json
import logging
import math
import os
import time
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

from charge_logic import (
    ChargeController,
    SESSION_FILE,
    SESSION_START_MAX_AGE,
)
from runtime.charge.evidence.first_stage import (
    FirstStageAssessment,
    FirstStageState,
    assess_first_stage,
    tail_current_threshold_a,
)
from runtime.charge.evidence.first_stage_variables import NEAR_TARGET_MARGIN_V
from application.recipe_policy import chemistry_for_profile
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision
from recovery_session import RecoveryTracePoint
from recovery_shadow import ShadowRecoveryRuntime
from signal_analyzer import SignalEvent
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.runtime.main_scaffold import run_authoritative_main_scaffold
from runtime.charge.runtime.variables import STAGE_TRANSITION_BLANKING_S
from runtime.charge.runtime.mix_scaffold import run_authoritative_mix_scaffold
from runtime.charge.runtime.recovery_scaffold import run_authoritative_recovery_scaffold
from runtime.charge.runtime.residual_scaffold import run_authoritative_residual_scaffold
from runtime.charge.strategy.desulfation import (
    DesulfationAction,
    decide_desulfation,
    select_desulfation_target,
)
from runtime.charge.strategy.desulfation_variables import desulfation_duration_seconds
from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitAction,
    FinalSafeWaitContinuation,
    decide_final_safe_wait,
    validate_final_continuation,
)
from runtime.charge.strategy.main_authority import decide_main_transition
from runtime.charge.strategy.mix import decide_mix_transition, select_mix_target
from runtime.charge.strategy.mix_variables import (
    mix_finish_hold_seconds,
    mix_max_active_seconds,
)
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitAction,
    RecoverySafeWaitContinuation,
    decide_recovery_safe_wait,
    validate_recovery_continuation,
)
from runtime.charge.strategy.safe_wait_variables import (
    SAFE_WAIT_TARGET_MARGIN_V,
    safe_wait_max_seconds,
)
from runtime.charge.strategy.storage import select_storage_target
from runtime.charge.strategy.main_variables import (
    AGM_MAX_RECOVERY_ATTEMPTS,
    AGM_PLATEAU_REQUIRED_MINUTES,
    AGM_STAGE_VOLTAGES_V,
    PLATEAU_EVIDENCE_WINDOW_MINUTES,
    STANDARD_MAX_RECOVERY_ATTEMPTS,
    STANDARD_PLATEAU_REQUIRED_MINUTES,
    agm_tail_hold_seconds,
    main_fallback_seconds,
    standard_tail_hold_seconds,
)
logger = logging.getLogger("rd6018.recovery")


# Compatibility alias for existing imports/tests; the semantic owner is modular.
INTERMEDIATE_RECOVERY_DURATION_SEC = desulfation_duration_seconds()


class ChargeControllerV2(ChargeController):
    """Transitional production controller while modular V3 replaces the old FSM.

    For non-Custom automatic charging, MAIN, bounded DESULFATION, recovery
    SAFE_WAIT, MIX, and final SAFE_WAIT now use modular strategy/runtime owners and
    do not enter historical ``ChargeController.tick()``. The superclass remains for
    compatibility state, persistence helpers, Cooling mechanics, and program
    families that have not yet been migrated.

    Production no longer accepts an environment switch back to historical
    transition authority. ``authoritative=False`` is retained only for isolated
    characterization/compatibility tests. Custom remains a separately migrated
    program family and is not a production rollback path.
    """

    def __init__(
        self,
        hass_client: Any,
        notify_cb: Optional[Callable[[str], Any]] = None,
        *,
        battery_id: Optional[str] = None,
        recovery_intent: ChargeIntent = ChargeIntent.RECOVERY,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
        authoritative: Optional[bool] = None,
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
        self._v2_trace_session_id: Optional[str] = None
        self._v2_trace_started_at: float = 0.0
        self._v2_main_plateau_since: Optional[float] = None
        self._recovery_safe_wait: Optional[RecoverySafeWaitContinuation] = None
        self._final_safe_wait: Optional[FinalSafeWaitContinuation] = None
        # Captured by the V2 tick and serialized by the production controller.
        self._v2_session_signal_context: Optional[Dict[str, Any]] = None
        # Production authority is fixed on the V2-authoritative path while the
        # remaining historical scaffold is extracted. Environment configuration may
        # not silently re-enable legacy transition ownership.
        self._v2_authoritative = True if authoritative is None else bool(authoritative)

    @property
    def v2_authoritative(self) -> bool:
        return bool(self._v2_authoritative)

    def set_v2_authoritative(self, enabled: bool) -> None:
        """Runtime rollback switch; changing it never mutates the current stage."""
        self._v2_authoritative = bool(enabled)
        logger.warning("V2 actuator authority set to %s", self._v2_authoritative)

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
        self._v2_last_disagreement = None
        self._v2_disagreement_repeat_count = 0
        self._v2_main_plateau_since = None
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

    def _begin_trace_identity(self) -> None:
        self._v2_trace_session_id = uuid.uuid4().hex
        self._v2_trace_started_at = float(self.total_start_time or time.time())

    def _initialize_shadow_session(self, *, started_at: Optional[float] = None) -> None:
        self._v2_session_signal_context = None
        runtime_started_at = float(
            started_at
            if started_at is not None and float(started_at) > 0
            else (self._v2_trace_started_at or self.total_start_time or time.time())
        )
        self._new_runtime(started_at=runtime_started_at)
        self._v2_last_disagreement = None
        self._v2_disagreement_repeat_count = 0
        self._v2_main_plateau_since = None
        try:
            target_v, _ = self._get_target_v_i()
            self._v2_target_voltage_v = float(target_v)
        except Exception:
            self._v2_target_voltage_v = None
        self._v2_last_stage = self.current_stage

    @staticmethod
    def _enum_or_default(enum_cls: Any, value: Any, default: Any) -> Any:
        try:
            return enum_cls(str(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_legacy_session_document() -> Dict[str, Any]:
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_trace_identity_to_session_file(self) -> None:
        if self.current_stage == self.STAGE_IDLE:
            return
        if not self._v2_trace_session_id or self._v2_trace_started_at <= 0:
            return
        document = self._read_legacy_session_document()
        if not document:
            return

        document["v2_trace_session_id"] = self._v2_trace_session_id
        document["v2_trace_started_at"] = self._v2_trace_started_at
        document["v2_battery_id"] = self._v2_battery_id
        document["v2_intent"] = self._v2_intent.value
        document["v2_condition_before"] = self._v2_condition_before.value
        document["v2_authoritative"] = self._v2_authoritative
        if self._recovery_safe_wait is not None:
            document["v2_recovery_safe_wait"] = self._recovery_safe_wait.as_dict()
        else:
            document.pop("v2_recovery_safe_wait", None)
        if self._final_safe_wait is not None:
            document["v2_final_safe_wait"] = self._final_safe_wait.as_dict()
        else:
            document.pop("v2_final_safe_wait", None)
        if self.current_stage == self.STAGE_DONE:
            document["terminal_session_id"] = self._v2_trace_session_id

        tmp_path = f"{SESSION_FILE}.v2.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, SESSION_FILE)
        except OSError as exc:
            logger.warning("Could not persist V2 trace identity: %s", exc)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _restore_trace_identity(self, document: Dict[str, Any]) -> None:
        raw_started_at = document.get("v2_trace_started_at")
        if raw_started_at is None:
            raw_started_at = document.get("total_start_time")
        if raw_started_at is None:
            raw_started_at = document.get("saved_at")
        try:
            started_at = float(raw_started_at)
        except (TypeError, ValueError):
            started_at = float(self.total_start_time or time.time())
        if not math.isfinite(started_at) or started_at <= 0:
            started_at = float(self.total_start_time or time.time())

        raw_id = str(document.get("v2_trace_session_id") or "").strip()
        if not raw_id:
            seed = "|".join(
                [
                    str(document.get("profile") or self.battery_type),
                    str(document.get("ah_limit") or self.ah_capacity),
                    f"{started_at:.6f}",
                    str(document.get("saved_at") or ""),
                ]
            )
            raw_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-recovery:{seed}").hex

        saved_battery_id = document.get("v2_battery_id")
        if saved_battery_id:
            self._v2_battery_id = str(saved_battery_id)
        self._v2_intent = self._enum_or_default(
            ChargeIntent,
            document.get("v2_intent"),
            self._v2_intent,
        )
        self._v2_condition_before = self._enum_or_default(
            BatteryCondition,
            document.get("v2_condition_before"),
            self._v2_condition_before,
        )
        self._v2_trace_session_id = raw_id
        self._v2_trace_started_at = started_at

    def _restore_recovery_safe_wait(self, document: Dict[str, Any]) -> None:
        self._recovery_safe_wait = None
        raw = document.get("v2_recovery_safe_wait")
        if isinstance(raw, dict):
            try:
                raw_generation = raw.get("session_generation")
                candidate = RecoverySafeWaitContinuation(
                    source_stage=str(raw.get("source_stage") or ""),
                    next_stage=str(raw.get("next_stage") or ""),
                    target_voltage_v=float(raw.get("target_voltage_v")),
                    target_current_a=float(raw.get("target_current_a")),
                    started_at=float(raw.get("started_at")),
                    session_id=(
                        str(raw.get("session_id") or self._v2_trace_session_id or "") or None
                    ),
                    session_generation=(
                        float(raw_generation)
                        if raw_generation is not None
                        else float(self._v2_trace_started_at)
                    ),
                    recovery_attempt=int(raw.get("recovery_attempt", self.antisulfate_count)),
                    agm_stage_idx=int(raw.get("agm_stage_idx", self._agm_stage_idx)),
                )
            except (TypeError, ValueError, OverflowError):
                candidate = None
            if (
                candidate is not None
                and validate_recovery_continuation(
                    candidate,
                    session_id=self._v2_trace_session_id,
                    session_generation=self._v2_trace_started_at,
                    expected_source_stage=self.STAGE_DESULFATION,
                    expected_next_stage=self.STAGE_MAIN,
                )
                and candidate.recovery_attempt == int(self.antisulfate_count)
                and candidate.agm_stage_idx == int(self._agm_stage_idx)
            ):
                self._recovery_safe_wait = candidate
            return

        # One-way migration of an already persisted pre-cutover recovery SAFE_WAIT.
        # SAFE_WAIT->MAIN is unique to intermediate recovery; final Mix uses DONE.
        if (
            self.current_stage == self.STAGE_SAFE_WAIT
            and self._safe_wait_next_stage == self.STAGE_MAIN
            and self._safe_wait_target_v > 0.0
            and self._safe_wait_target_i > 0.0
            and self._safe_wait_start > 0.0
        ):
            self._recovery_safe_wait = RecoverySafeWaitContinuation(
                source_stage=self.STAGE_DESULFATION,
                next_stage=self.STAGE_MAIN,
                target_voltage_v=float(self._safe_wait_target_v),
                target_current_a=float(self._safe_wait_target_i),
                started_at=float(self._safe_wait_start),
                session_id=self._v2_trace_session_id,
                session_generation=float(self._v2_trace_started_at),
                recovery_attempt=int(self.antisulfate_count),
                agm_stage_idx=int(self._agm_stage_idx),
            )

    def _restore_final_safe_wait(self, document: Dict[str, Any]) -> None:
        self._final_safe_wait = None
        raw = document.get("v2_final_safe_wait")
        if isinstance(raw, dict):
            try:
                raw_generation = raw.get("session_generation")
                candidate = FinalSafeWaitContinuation(
                    source_stage=str(raw.get("source_stage") or ""),
                    next_stage=str(raw.get("next_stage") or ""),
                    target_voltage_v=float(raw.get("target_voltage_v")),
                    target_current_a=float(raw.get("target_current_a")),
                    started_at=float(raw.get("started_at")),
                    session_id=(
                        str(raw.get("session_id") or self._v2_trace_session_id or "") or None
                    ),
                    completion_reason=str(raw.get("completion_reason") or ""),
                    session_generation=(
                        float(raw_generation)
                        if raw_generation is not None
                        else float(self._v2_trace_started_at)
                    ),
                )
            except (TypeError, ValueError, OverflowError):
                candidate = None
            if (
                candidate is not None
                and validate_final_continuation(
                    candidate,
                    session_id=self._v2_trace_session_id,
                    session_generation=self._v2_trace_started_at,
                    expected_next_stage=self.STAGE_DONE,
                    allowed_source_stages={self.STAGE_MAIN, self.STAGE_MIX},
                )
            ):
                self._final_safe_wait = candidate
            return

        # One-way migration for a successful pre-cutover final SAFE_WAIT. Recovery
        # SAFE_WAIT is distinguished by next=MAIN and was reconstructed above.
        if (
            self.current_stage == self.STAGE_SAFE_WAIT
            and self._safe_wait_next_stage == self.STAGE_DONE
            and self._safe_wait_target_v > 0.0
            and self._safe_wait_target_i > 0.0
            and self._safe_wait_start > 0.0
        ):
            source_stage = str(self.previous_stage or self.STAGE_MIX)
            if source_stage not in {self.STAGE_MAIN, self.STAGE_MIX}:
                return
            self._final_safe_wait = FinalSafeWaitContinuation(
                source_stage=source_stage,
                next_stage=self.STAGE_DONE,
                target_voltage_v=float(self._safe_wait_target_v),
                target_current_a=float(self._safe_wait_target_i),
                started_at=float(self._safe_wait_start),
                session_id=self._v2_trace_session_id,
                completion_reason=str(self._last_transition_reason or "restored_successful_completion"),
                session_generation=float(self._v2_trace_started_at),
            )

    def start(self, battery_type: str, ah_capacity: int) -> None:
        if self._v2_authoritative and str(battery_type) == self.PROFILE_CUSTOM:
            raise RuntimeError(
                "historical Custom controller start is retired; use ProductionManualSessionManager"
            )
        self._recovery_safe_wait = None
        self._final_safe_wait = None
        super().start(battery_type, ah_capacity)
        self._begin_trace_identity()
        self._initialize_shadow_session(started_at=self._v2_trace_started_at)

    def start_custom(
        self,
        main_voltage: float,
        main_current: float,
        delta_threshold: float,
        time_limit_hours: float,
        ah_capacity: int,
    ) -> None:
        """Characterization-only adapter; production Custom is owned by Manual."""
        if self._v2_authoritative:
            raise RuntimeError(
                "historical Custom controller start is retired; use ProductionManualSessionManager"
            )
        self._recovery_safe_wait = None
        self._final_safe_wait = None
        super().start_custom(
            main_voltage=main_voltage,
            main_current=main_current,
            delta_threshold=delta_threshold,
            time_limit_hours=time_limit_hours,
            ah_capacity=ah_capacity,
        )
        self._begin_trace_identity()
        self._initialize_shadow_session(started_at=self._v2_trace_started_at)

    def _save_session(self, voltage: float, current: float, ah: float) -> None:
        super()._save_session(voltage, current, ah)
        self._write_trace_identity_to_session_file()

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
        trace_document = self._read_legacy_session_document()
        ok, message = super().try_restore_session(voltage, current, ah)
        if ok and self._v2_authoritative and self.battery_type == self.PROFILE_CUSTOM:
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
            self._restore_desulfation_stage_clock(trace_document)
            self._restore_trace_identity(trace_document)
            self._restore_recovery_safe_wait(trace_document)
            self._restore_final_safe_wait(trace_document)
            self._initialize_shadow_session(started_at=self._v2_trace_started_at)
            self._write_trace_identity_to_session_file()
        return ok, message

    @property
    def recovery_trace_context(self) -> Dict[str, Any]:
        started_at = float(self._v2_trace_started_at or self.total_start_time or 0.0)
        battery_id = self._v2_battery_id or f"anonymous:{self.battery_type}:{self.ah_capacity}"
        session_id = self._v2_trace_session_id
        if not session_id:
            seed = f"{battery_id}|{self.battery_type}|{self.ah_capacity}|{started_at:.6f}"
            session_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rd6018-volatile:{seed}").hex
        return {
            "session_id": session_id,
            "started_at": started_at,
            "battery_id": battery_id,
            "battery_type": self.battery_type,
            "capacity_ah": float(self.ah_capacity or 0.0),
            "intent": self._v2_intent,
            "condition_before": self._v2_condition_before,
            "authoritative": self._v2_authoritative,
        }

    async def _persist_shadow_trace_if_ready(self, shadow: Dict[str, Any]) -> bool:
        import database

        if not getattr(database, "TRACE_CAPTURE_READY", False):
            return False
        trace = shadow.get("trace_point")
        if not isinstance(trace, dict):
            return False
        if str(trace.get("stage") or "") == self.STAGE_IDLE:
            return False

        context = self.recovery_trace_context
        if float(context["started_at"]) <= 0:
            return False

        from recovery_trace_store import record_shadow_trace

        await record_shadow_trace(
            session_id=context["session_id"],
            started_at=context["started_at"],
            battery_id=context["battery_id"],
            battery_type=context["battery_type"],
            capacity_ah=context["capacity_ah"],
            intent=context["intent"],
            condition_before=context["condition_before"],
            shadow=shadow,
        )
        return True

    @staticmethod
    def _finite_or_nan(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return math.nan
        return parsed if math.isfinite(parsed) else math.nan

    @staticmethod
    def _finite_or_none(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @staticmethod
    def _normalize_output_on(value: Any) -> Optional[bool]:
        if value is None:
            return None
        raw = str(value).strip().lower()
        if value is True or raw == "on":
            return True
        if value is False or raw == "off":
            return False
        return None

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

    def _trace_point_metadata(
        self,
        *,
        timestamp_s: float,
        stage_before: str,
        stage_after: str,
        target_before: Optional[float],
        voltage: Any,
        current: Any,
        temp_ext: Any,
        is_cv: bool,
        is_cc: Optional[bool],
        ah: Any,
        output_is_on: Any,
    ) -> Dict[str, Any]:
        return {
            "timestamp_s": float(timestamp_s),
            "stage": str(stage_before),
            "legacy_stage_after": str(stage_after),
            "voltage_v": self._finite_or_none(voltage),
            "current_a": self._finite_or_none(current),
            "temp_c": self._finite_or_none(temp_ext),
            "is_cv": bool(is_cv),
            "is_cc": bool(is_cc) if is_cc is not None else None,
            "target_voltage_v": self._finite_or_none(target_before),
            "ah": self._finite_or_none(ah),
            "output_on": self._normalize_output_on(output_is_on),
        }

    def _shadow_metadata(
        self,
        record: Any,
        *,
        trace_point: Dict[str, Any],
        first_stage: Optional[FirstStageAssessment] = None,
        authority_decision: Optional[AuthorityDecision] = None,
    ) -> Dict[str, Any]:
        metrics = record.analysis.metrics
        payload = {
            "status": "ok",
            "decision": record.decision.decision.value,
            "reason": record.decision.reason,
            "events": sorted(event.value for event in record.analysis.events),
            "disagreement": record.disagreement,
            "legacy_effect": record.legacy_effect,
            "authority": "v2" if self._v2_authoritative else "legacy",
            "trace_point": trace_point,
            "metrics": {
                "d_voltage_v_per_min": metrics.d_voltage_v_per_min,
                "d_current_a_per_min": metrics.d_current_a_per_min,
                "d_temp_c_per_min": metrics.d_temp_c_per_min,
                "current_min_a": metrics.current_min_a,
                "seconds_since_current_min": metrics.seconds_since_current_min,
                "delta_current_from_min_a": metrics.delta_current_from_min_a,
                "reversal_threshold_a": metrics.reversal_threshold_a,
                "reversal_confirmations": metrics.reversal_confirmations,
                "voltage_max_v": metrics.voltage_max_v,
                "seconds_since_voltage_max": metrics.seconds_since_voltage_max,
                "delta_voltage_from_max_v": metrics.delta_voltage_from_max_v,
                "voltage_reversal_threshold_v": metrics.voltage_reversal_threshold_v,
                "voltage_reversal_confirmations": metrics.voltage_reversal_confirmations,
            },
        }
        if first_stage is not None:
            payload["first_stage"] = self._first_stage_metadata(first_stage)
        if authority_decision is not None:
            payload["authority_decision"] = {
                "action": authority_decision.action.value,
                "reason": authority_decision.reason,
            }
        return payload

    def _update_main_plateau_clock(
        self,
        *,
        stage_before: str,
        target_before: Optional[float],
        timestamp_s: float,
        voltage: float,
        current: float,
        is_cv: bool,
        record: Any,
    ) -> Optional[float]:
        if stage_before != self.STAGE_MAIN or target_before is None or not is_cv:
            self._v2_main_plateau_since = None
            return None
        try:
            threshold = tail_current_threshold_a(
                chemistry_for_profile(self.battery_type),
                float(self.ah_capacity),
            )
            near_target = float(voltage) >= float(target_before) - float(NEAR_TARGET_MARGIN_V.default)
        except (TypeError, ValueError):
            self._v2_main_plateau_since = None
            return None

        events = record.analysis.events
        if SignalEvent.CURRENT_MINIMUM_UPDATED in events:
            self._v2_main_plateau_since = None
            return None
        qualifies = (
            near_target
            and float(current) > threshold
            and SignalEvent.CURRENT_PLATEAU in events
        )
        if not qualifies:
            self._v2_main_plateau_since = None
            return None
        if self._v2_main_plateau_since is None:
            # CURRENT_PLATEAU itself is based on a 15-minute window.  Backdate the
            # first plateau timestamp by that evidence window so a 40-minute rule
            # remains approximately 40 minutes rather than silently becoming 55.
            self._v2_main_plateau_since = max(0.0, float(timestamp_s) - float(PLATEAU_EVIDENCE_WINDOW_MINUTES.default) * 60.0)
        return self._v2_main_plateau_since

    def _assess_main_sample(
        self,
        *,
        stage_before: str,
        target_before: Optional[float],
        plateau_since: Optional[float],
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

        plateau_minutes = 0.0
        if plateau_since is not None:
            plateau_minutes = max(0.0, (timestamp_s - float(plateau_since)) / 60.0)
        required_plateau = (
            float(AGM_PLATEAU_REQUIRED_MINUTES.default)
            if self.battery_type == self.PROFILE_AGM
            else float(STANDARD_PLATEAU_REQUIRED_MINUTES.default)
        )
        metrics = record.analysis.metrics
        return assess_first_stage(
            chemistry=chemistry_for_profile(self.battery_type),
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
            temperature_c=getattr(getattr(record.analysis, "sample", None), "temp_c", None),
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
        if self._v2_disagreement_repeat_count != 1 and self._v2_disagreement_repeat_count % 20 != 0:
            return
        logger.warning(
            "RECOVERY_SHADOW disagreement=%s repeats=%d decision=%s legacy=%s stage=%s reason=%s",
            disagreement,
            self._v2_disagreement_repeat_count,
            record.decision.decision.value,
            record.legacy_effect,
            stage,
            record.decision.reason,
        )

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
        owner = "v2" if self._v2_authoritative else "legacy"
        logger.info(
            "CHARGE_TRANSITION old=%s new=%s reason=%s owner=%s timestamp=%.3f",
            old_stage,
            new_stage,
            reason or "unspecified",
            owner,
            float(timestamp_s),
        )

    def _complete_desulfation_to_safe_wait(
        self,
        *,
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        actions: Dict[str, Any],
    ) -> None:
        elapsed = max(0.0, float(now) - float(self.stage_start_time))
        actions["log_event_end"] = self._make_log_event_end(
            now,
            ah,
            voltage,
            current,
            temp,
            "bounded intermediate recovery 2h complete",
        )
        target_v, target_i = self._main_target(temp)
        continuation = RecoverySafeWaitContinuation(
            source_stage=self.STAGE_DESULFATION,
            next_stage=self.STAGE_MAIN,
            target_voltage_v=float(target_v),
            target_current_a=float(target_i),
            started_at=float(now),
            session_id=self._v2_trace_session_id,
            recovery_attempt=int(self.antisulfate_count),
            agm_stage_idx=int(self._agm_stage_idx),
            session_generation=float(self._v2_trace_started_at),
        )
        self._recovery_safe_wait = continuation
        self.current_stage = self.STAGE_SAFE_WAIT
        self._clear_restored_targets()
        self.stage_start_time = now
        self._stage_start_ah = ah
        # Compatibility mirrors for existing persistence/UI readers only.
        self._safe_wait_next_stage = continuation.next_stage
        self._safe_wait_target_v = continuation.target_voltage_v
        self._safe_wait_target_i = continuation.target_current_a
        self._safe_wait_start = continuation.started_at
        self._record_safe_wait_sample(now, voltage, current, temp)
        self._v2_main_plateau_since = None
        actions["turn_off"] = True
        threshold = (
            continuation.target_voltage_v
            - float(SAFE_WAIT_TARGET_MARGIN_V.default)
        )
        actions["notify"] = (
            f"<b>⏸ Десульфатация завершена.</b> Ожидание падения до {threshold:.1f}В. "
            "Выход выключен."
        )
        actions["log_event"] = "START | INTERMEDIATE_RECOVERY_COMPLETE"
        logger.info(
            "V2 intermediate recovery complete stage=%s elapsed=%.1fs attempt=%d agm_step=%d",
            self.STAGE_DESULFATION,
            elapsed,
            continuation.recovery_attempt,
            continuation.agm_stage_idx,
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
            self._stop_and_diagnose(
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
        output_is_off = self._normalize_output_on(output_is_on) is False
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
        continuation = self._final_safe_wait
        valid = (
            continuation is not None
            and self.current_stage == self.STAGE_SAFE_WAIT
            and validate_final_continuation(
                continuation,
                session_id=self._v2_trace_session_id,
                session_generation=self._v2_trace_started_at,
                expected_next_stage=self.STAGE_DONE,
                allowed_source_stages={self.STAGE_MAIN, self.STAGE_MIX},
            )
        )
        if not valid:
            reason = "final_safe_wait_continuation_invalid"
            self._stop_and_diagnose(
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

        assert continuation is not None
        output_is_off = self._normalize_output_on(output_is_on) is False
        if output_is_off:
            self._record_safe_wait_sample(now, voltage, current, temp)
        decision = decide_final_safe_wait(
            continuation,
            now_s=now,
            voltage_v=voltage,
            output_is_off=output_is_off,
        )
        if decision.action == FinalSafeWaitAction.WAIT:
            return AuthorityDecision(AuthorityAction.CONTINUE, decision.reason)

        actions["set_voltage"] = continuation.target_voltage_v
        actions["set_current"] = continuation.target_current_a
        self._add_phase_limits(
            actions,
            continuation.target_voltage_v,
            continuation.target_current_a,
        )
        actions["turn_on"] = True
        # Storage/DONE remains a two-phase transition: this token is only a request.
        # The execution layer must prove programmed readback and physical Output ON
        # before commit_verified_enable_transition may advance the software stage.
        actions["verified_enable_transition"] = {
            "kind": "final_safe_wait_to_done",
            "session_id": continuation.session_id,
            "session_generation": continuation.session_generation,
            "started_at": continuation.started_at,
            "reason": decision.reason,
        }
        actions["log_event"] = "FINAL_SAFE_WAIT_STORAGE_ENABLE_ATTEMPT"
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
            not self._v2_authoritative
            or self.battery_type == self.PROFILE_CUSTOM
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
            continuation = self._final_safe_wait
            if continuation is None or self.current_stage != self.STAGE_SAFE_WAIT:
                logger.error("verified final completion rejected: no matching SAFE_WAIT continuation")
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
                or abs(
                    token_session_generation
                    - float(continuation.session_generation)
                ) > 1e-6
                or abs(
                    token_session_generation
                    - float(self._v2_trace_started_at)
                ) > 1e-6
            ):
                logger.error("verified final completion rejected: continuation token mismatch")
                return None

            self.current_stage = self.STAGE_DONE
            self._clear_restored_targets()
            self.stage_start_time = float(now)
            self._stage_start_ah = float(ah)
            self._safe_wait_next_stage = None
            self._safe_wait_target_v = 0.0
            self._safe_wait_target_i = 0.0
            self._safe_wait_start = 0.0
            self._final_safe_wait = None
            self._recovery_safe_wait = None
            self._done_transition_source_stage = self.STAGE_SAFE_WAIT
            try:
                self._save_session(float(voltage), float(current), float(ah))
            finally:
                self._done_transition_source_stage = None
            return {
                "log_event": "START | V2_STORAGE_OUTPUT_VERIFIED",
                "notify": "<b>✅ Заряд завершён.</b> Storage включён и подтверждён.",
            }
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
        self._v2_main_plateau_since = None
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
        entirely; this hook remains only for characterization/direct legacy callers.
        """
        return bool(
            self._v2_authoritative
            and self.battery_type != self.PROFILE_CUSTOM
            and self.current_stage == self.STAGE_MIX
        )

    def _is_authoritative_stage(self, stage: str) -> bool:
        return (
            self._v2_authoritative
            and self.battery_type != self.PROFILE_CUSTOM
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
        if self._v2_authoritative and self.battery_type == self.PROFILE_CUSTOM:
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
            self._v2_authoritative
            and self.battery_type != self.PROFILE_CUSTOM
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
            self._v2_authoritative
            and self.battery_type != self.PROFILE_CUSTOM
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
            self._v2_authoritative
            and self.battery_type != self.PROFILE_CUSTOM
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
            "Historical controller fallback retired; rejecting stage=%s profile=%s",
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

    def _enter_safe_wait_done(
        self,
        *,
        actions: Dict[str, Any],
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        reason: str,
    ) -> None:
        prev = self.current_stage
        actions["log_event_end"] = self._make_log_event_end(
            now, ah, voltage, current, temp, reason
        )
        uv, ui = self._storage_target()
        threshold = uv - float(SAFE_WAIT_TARGET_MARGIN_V.default)
        self.current_stage = self.STAGE_SAFE_WAIT
        self._clear_restored_targets()
        self.stage_start_time = now
        self._stage_start_ah = ah
        self._safe_wait_next_stage = self.STAGE_DONE
        self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
        self._safe_wait_start = now
        self._final_safe_wait = FinalSafeWaitContinuation(
            source_stage=prev,
            next_stage=self.STAGE_DONE,
            target_voltage_v=float(uv),
            target_current_a=float(ui),
            started_at=float(now),
            session_id=self._v2_trace_session_id,
            completion_reason=str(reason),
            session_generation=float(self._v2_trace_started_at),
        )
        self._recovery_safe_wait = None
        self._record_safe_wait_sample(now, voltage, current, temp)
        self.finish_timer_start = None
        self._v2_main_plateau_since = None
        actions["turn_off"] = True
        actions["notify"] = (
            f"<b>✅ V2: этап завершён.</b> {reason}. "
            f"Ожидание падения до {threshold:.1f}В перед Storage."
        )
        actions["log_event"] = "START | V2_AUTHORITATIVE"
        logger.info("V2 transition %s -> %s | %s", prev, self.STAGE_SAFE_WAIT, reason)

    def _stop_and_diagnose(
        self,
        *,
        actions: Dict[str, Any],
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        reason: str,
    ) -> None:
        prev = self.current_stage
        self._recovery_safe_wait = None
        self._final_safe_wait = None
        actions["log_event_end"] = self._make_log_event_end(
            now, ah, voltage, current, temp, reason
        )
        self.current_stage = self.STAGE_DONE
        self._clear_restored_targets()
        self.stage_start_time = now
        self._stage_start_ah = ah
        self.finish_timer_start = None
        self._v2_main_plateau_since = None
        actions["turn_off"] = True
        actions["notify"] = (
            "<b>🛑 V2 остановил автоматическую эскалацию.</b>\n"
            f"Причина: <code>{reason}</code>.\n"
            "Выход выключен; требуется оценка графика/АКБ перед новым HV-этапом."
        )
        actions["log_event"] = "V2_STOP_DIAGNOSE"
        self._save_session(voltage, current, ah)
        logger.warning("V2 diagnostic stop %s -> Done | %s", prev, reason)

    def _advance_agm_step(
        self,
        *,
        actions: Dict[str, Any],
        now: float,
        temp: float,
        ah: float,
        reason: str,
    ) -> None:
        self._agm_stage_idx = min(self._agm_stage_idx + 1, len(AGM_STAGE_VOLTAGES_V.default) - 1)
        self.stage_start_time = now
        self._stage_start_ah = ah
        self._reset_delta_and_blanking(now)
        self._v2_main_plateau_since = None
        uv, ui = self._main_target(temp)
        actions["set_voltage"] = uv
        actions["set_current"] = ui
        self._add_phase_limits(actions, uv, ui)
        actions["notify"] = (
            f"<b>🚀 V2 AGM ступень {self._agm_stage_idx + 1}/{len(AGM_STAGE_VOLTAGES_V.default)}:</b> "
            f"{uv:.2f}В / {ui:.2f}А — {reason}."
        )
        actions["log_event"] = f"V2_AGM_STEP_{self._agm_stage_idx + 1}"

    def _enter_desulfation(
        self,
        *,
        actions: Dict[str, Any],
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        reason: str,
    ) -> None:
        prev = self.current_stage
        self.antisulfate_count += 1
        actions["log_event_end"] = self._make_log_event_end(
            now, ah, voltage, current, temp, reason
        )
        self.current_stage = self.STAGE_DESULFATION
        self._clear_restored_targets()
        self.stage_start_time = now
        self._stage_start_ah = ah
        self._reset_delta_and_blanking(now)
        self._v2_main_plateau_since = None
        dv, di = self._desulf_target(temp)
        actions["set_voltage"] = dv
        actions["set_current"] = di
        self._add_desulf_limits(actions, dv, di)
        actions["notify"] = (
            f"🔧 <b>V2 десульфатация #{self.antisulfate_count}</b>\n"
            f"{reason}\nЦель: {dv:.2f}В / {di:.2f}А на сервисный этап."
        )
        actions["log_event"] = "START | V2_DESULFATION"
        logger.info("V2 transition %s -> %s | %s", prev, self.STAGE_DESULFATION, reason)

    def _enter_mix(
        self,
        *,
        actions: Dict[str, Any],
        now: float,
        voltage: float,
        current: float,
        temp: float,
        ah: float,
        reason: str,
    ) -> None:
        prev = self.current_stage
        actions["log_event_end"] = self._make_log_event_end(
            now, ah, voltage, current, temp, reason
        )
        self.current_stage = self.STAGE_MIX
        self._clear_restored_targets()
        self.stage_start_time = now
        self._stage_start_ah = ah
        self._reset_delta_and_blanking(now)
        self._v2_main_plateau_since = None
        self.finish_timer_start = None
        self._delta_reported = False
        if hasattr(self, "_finish_evidence"):
            self._finish_evidence = None
        mxv, mxi = self._mix_target(temp)
        actions["set_voltage"] = mxv
        actions["set_current"] = mxi
        self._add_phase_limits(actions, mxv, mxi)
        actions["notify"] = (
            f"<b>🚀 V2 → Mix Mode</b>\n{reason}\n"
            f"Цель: {mxv:.2f}В / {mxi:.2f}А; выход по CV ΔI или CC ΔV."
        )
        actions["log_event"] = "START | V2_MIX"
        logger.info("V2 transition %s -> %s | %s", prev, self.STAGE_MIX, reason)

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
                self._complete_desulfation_to_safe_wait(
                    now=timestamp_s,
                    voltage=voltage,
                    current=current,
                    temp=temp,
                    ah=ah,
                    actions=actions,
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
            required_hold = (
                agm_tail_hold_seconds()
                if self.battery_type == self.PROFILE_AGM
                else standard_tail_hold_seconds()
            )
            max_desulf = (
                int(AGM_MAX_RECOVERY_ATTEMPTS.default)
                if self.battery_type == self.PROFILE_AGM
                else int(STANDARD_MAX_RECOVERY_ATTEMPTS.default)
            )
            decision = decide_main_transition(
                profile=self.battery_type,
                intent=self._v2_intent,
                first_stage=first_stage,
                policy_decision=record.decision.decision,
                seconds_since_current_min=record.analysis.metrics.seconds_since_current_min,
                required_tail_hold_s=required_hold,
                agm_stage_idx=self._agm_stage_idx,
                agm_stage_count=len(AGM_STAGE_VOLTAGES_V.default),
                desulf_attempts=self.antisulfate_count,
                max_desulf_attempts=max_desulf,
                main_elapsed_s=max(0.0, float(timestamp_s) - float(self.stage_start_time)),
                main_limit_s=main_fallback_seconds(),
                current_a=float(current),
                is_cv=bool(is_cv),
            )
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

        # Mix: expose V2 mode-specific evidence through the legacy-compatible fields
        # used by the existing Telegram dashboard while V2 owns the actual decision.
        metrics = record.analysis.metrics
        if is_cv and metrics.current_min_a is not None:
            self.i_min_recorded = metrics.current_min_a
        if is_cc and metrics.voltage_max_v is not None:
            self.v_max_recorded = metrics.voltage_max_v

        decision = decide_mix_transition(
            profile=self.battery_type,
            policy_decision=record.decision.decision,
            active_elapsed_s=max(0.0, timestamp_s - self.stage_start_time),
            authority_limit_s=self._mix_limit_seconds(),
            finish_hold_started_at=self.finish_timer_start,
            now_s=timestamp_s,
            finish_hold_s=mix_finish_hold_seconds(),
        )
        if decision.action == AuthorityAction.START_FINISH_HOLD:
            self.finish_timer_start = timestamp_s
            self._delta_reported = True
            self._delta_trigger_mode = "CC" if is_cc else ("CV" if is_cv else None)
            if hasattr(self, "_finish_evidence") and self._delta_trigger_mode in {"CV", "CC"}:
                reference = metrics.voltage_max_v if is_cc else metrics.current_min_a
                accepted_delta = metrics.delta_voltage_from_max_v if is_cc else metrics.delta_current_from_min_a
                if reference is not None and accepted_delta is not None:
                    self._finish_evidence = {
                        "version": 1,
                        "mode": self._delta_trigger_mode,
                        "reference_value": float(reference),
                        "accepted_delta": float(accepted_delta),
                        "accepted_at": float(timestamp_s),
                        "session_id": self._v2_trace_session_id,
                    }
            if is_cc:
                evidence = (
                    f"Vmax={metrics.voltage_max_v:.3f}В, "
                    f"ΔV={metrics.delta_voltage_from_max_v:.3f}В"
                    if metrics.voltage_max_v is not None
                    and metrics.delta_voltage_from_max_v is not None
                    else "CC ΔV подтверждена"
                )
            else:
                evidence = (
                    f"Imin={metrics.current_min_a:.3f}А, "
                    f"ΔI={metrics.delta_current_from_min_a:.3f}А"
                    if metrics.current_min_a is not None
                    and metrics.delta_current_from_min_a is not None
                    else "CV ΔI подтверждена"
                )
            actions["notify"] = (
                f"<b>🎯 V2 Delta подтверждена</b> ({'CC' if is_cc else 'CV'}).\n"
                f"{evidence}\nSticky finish-hold: 2ч."
            )
            actions["log_event"] = f"V2_FINISH_HOLD_START | {evidence}"
            logger.info(
                "CHARGE_EVIDENCE kind=delta event=hold_start mode=%s hold_seconds=%.1f timestamp=%.3f",
                self._delta_trigger_mode or "unknown",
                mix_finish_hold_seconds(),
                timestamp_s,
            )
        elif decision.action == AuthorityAction.COMPLETE_TO_SAFE_WAIT:
            if self.finish_timer_start is not None:
                logger.info(
                    "CHARGE_EVIDENCE kind=delta event=hold_complete mode=%s hold_seconds=%.1f timestamp=%.3f",
                    self._delta_trigger_mode or "unknown",
                    max(0.0, timestamp_s - float(self.finish_timer_start)),
                    timestamp_s,
                )
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
            logger.info(
                "CHARGE_EVIDENCE kind=stop event=diagnose reason=%s owner=v2 timestamp=%.3f",
                decision.reason,
                timestamp_s,
            )
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

        actions = await self._run_stage_scaffold_tick(
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
                    voltage_v=self._finite_or_nan(voltage),
                    current_a=self._finite_or_nan(current),
                    temp_c=self._finite_or_nan(temp_ext),
                    is_cv=bool(is_cv),
                    is_cc=resolved_is_cc,
                    target_voltage_v=target_before,
                    ah=self._finite_or_nan(ah),
                ),
                legacy_actions=actions,
                output_is_on=self._normalize_output_on(output_is_on),
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
            self._v2_session_signal_context = {
                "stage": str(stage_before),
                "mode": mode,
                "session_id": self._v2_trace_session_id,
                "session_generation": float(self._v2_trace_started_at or 0.0),
                "output_on": self._normalize_output_on(output_is_on),
                "cv_state": bool(is_cv),
                "cc_state": bool(resolved_is_cc),
                "telemetry_valid": not record.analysis.has(SignalEvent.TELEMETRY_INVALID),
                "telemetry_observed_at": float(timestamp_s),
                "telemetry_age_s": max(0.0, time.time() - float(timestamp_s)),
                "target_voltage_v": target_before,
                "current_min_a": metrics.current_min_a,
                "current_min_time_s": (
                    float(timestamp_s) - float(analyzer._current_min_time_s)
                    if analyzer is not None and analyzer._current_min_time_s is not None
                    else None
                ),
                "delta_reference_a": metrics.current_min_a,
                "voltage_max_v": metrics.voltage_max_v,
                "voltage_max_time_s": (
                    float(timestamp_s) - float(analyzer._voltage_max_time_s)
                    if analyzer is not None and analyzer._voltage_max_time_s is not None
                    else None
                ),
                "delta_reference_v": metrics.voltage_max_v,
                "reversal_threshold_a": metrics.reversal_threshold_a,
                "reversal_confirmations": metrics.reversal_confirmations,
                "last_reversal_confirmation_s": (
                    analyzer._last_reversal_confirmation_s if analyzer is not None else None
                ),
                "reversal_emitted": bool(analyzer._reversal_emitted) if analyzer is not None else False,
                "voltage_reversal_confirmations": (
                    metrics.voltage_reversal_confirmations
                ),
                "voltage_last_reversal_confirmation_s": (
                    analyzer._last_voltage_reversal_confirmation_s
                    if analyzer is not None
                    else None
                ),
                "voltage_reversal_emitted": (
                    bool(analyzer._voltage_reversal_emitted)
                    if analyzer is not None
                    else False
                ),
            }

            plateau_since = self._update_main_plateau_clock(
                stage_before=stage_before,
                target_before=target_before,
                timestamp_s=timestamp_s,
                voltage=voltage,
                current=current,
                is_cv=is_cv,
                record=record,
            )
            first_stage = self._assess_main_sample(
                stage_before=stage_before,
                target_before=target_before,
                plateau_since=plateau_since,
                timestamp_s=timestamp_s,
                voltage=voltage,
                current=current,
                is_cv=is_cv,
                record=record,
            )

            if self._is_authoritative_stage(stage_before):
                if temp_ext is None:
                    temp_value = math.nan
                else:
                    temp_value = self._finite_or_nan(temp_ext)
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
                self._log_shadow_disagreement(record, stage=stage_before)

            trace_point = self._trace_point_metadata(
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
            )
            actions["recovery_shadow"] = self._shadow_metadata(
                record,
                trace_point=trace_point,
                first_stage=first_stage,
                authority_decision=authority_decision,
            )
        except Exception as exc:
            # In legacy-fallback mode evidence remains diagnostic-only. In V2 authority
            # mode a failed evidence path must fail closed instead of silently handing
            # transition control back to legacy and possibly escalating voltage.
            logger.exception("RECOVERY_V2 observation/authority failed")
            self._v2_session_signal_context = None
            trace_point = self._trace_point_metadata(
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
            )
            actions["recovery_shadow"] = {
                "status": "error",
                "decision": None,
                "reason": "V2 observation/authority failed",
                "error_type": type(exc).__name__,
                "authority": "v2" if self._v2_authoritative else "legacy",
                "trace_point": trace_point,
            }
            if self._is_authoritative_stage(stage_before) and self.current_stage == stage_before:
                temp_value = self._finite_or_nan(temp_ext)
                if math.isfinite(temp_value):
                    self._stop_and_diagnose(
                        actions=actions,
                        now=timestamp_s,
                        voltage=self._finite_or_nan(voltage),
                        current=self._finite_or_nan(current),
                        temp=temp_value,
                        ah=self._finite_or_nan(ah),
                        reason=f"v2_internal_error:{type(exc).__name__}",
                    )
                else:
                    actions["emergency_stop"] = True
                    actions["turn_off"] = True

        try:
            if await self._persist_shadow_trace_if_ready(actions["recovery_shadow"]):
                actions["recovery_shadow"]["persistence"] = "stored"
        except Exception as exc:
            logger.exception("RECOVERY_TRACE persistence failed; actuator decision remains valid")
            actions["recovery_shadow"]["persistence"] = "error"
            actions["recovery_shadow"]["persistence_error_type"] = type(exc).__name__

        next_target = actions.get("set_voltage")
        if next_target is not None:
            self._v2_target_voltage_v = self._finite_or_nan(next_target)
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
        if self._v2_authoritative and self.current_stage not in {self.STAGE_IDLE, self.STAGE_DONE}:
            self._save_session(float(voltage), float(current), float(ah))

        return actions

    def v2_ui_snapshot(self) -> Dict[str, Any]:
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
            "authoritative": self._v2_authoritative,
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
        snapshot = self.v2_ui_snapshot()
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
                "authoritative": self._v2_authoritative,
            }
        summary = dict(self._v2_runtime.summary())
        summary["last_disagreement"] = self._v2_last_disagreement
        summary["last_disagreement_repeats"] = self._v2_disagreement_repeat_count
        summary["authoritative"] = self._v2_authoritative
        return summary
