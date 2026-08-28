from __future__ import annotations

import json
import logging
import math
import os
import time
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

from charge_logic import (
    AGM_FIRST_STAGE_HOLD_SEC,
    AGM_MIX_MAX_HOURS,
    AGM_STAGES,
    ANTISULFATE_MAX_AGM,
    ANTISULFATE_MAX_CA_EFB,
    BLANKING_SEC,
    CA_MIX_MAX_HOURS,
    ChargeController,
    EFB_MIX_MAX_HOURS,
    FIRST_STAGE_HOLD_SEC,
    MIX_DONE_TIMER,
    SAFE_WAIT_V_MARGIN,
    SESSION_FILE,
)
from first_stage_evidence import (
    FirstStageAssessment,
    FirstStageState,
    assess_first_stage,
    tail_current_threshold_a,
)
from legacy_recipe_adapter import chemistry_for_legacy_profile
from legacy_transition_audit import LegacyTransitionAudit, TransitionAuditSeverity, audit_legacy_transition
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision
from recovery_session import RecoveryTracePoint
from recovery_shadow import ShadowRecoveryRuntime
from signal_analyzer import SignalEvent
from v2_authority import (
    AuthorityAction,
    AuthorityDecision,
    decide_main_transition,
    decide_mix_transition,
)

logger = logging.getLogger("rd6018.recovery")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in {"0", "false", "no", "off", "disabled"}


class ChargeControllerV2(ChargeController):
    """Production V2 controller with a legacy safety/mechanics fallback.

    Default production mode is V2-authoritative for non-Custom Main/Mix transitions.
    The proven legacy controller is still called as the common safety/mechanics
    scaffold (telemetry validation, hard Main timeout, temperature protection,
    SAFE_WAIT/Cooling/restore/session persistence), but its Main/Mix transition
    triggers are masked before that call.  V2 evidence then owns those transitions.

    Set ``V2_AUTHORITATIVE=0`` (or pass ``authoritative=False``) for an emergency
    rollback to the previous legacy-authoritative + V2-shadow behaviour.  Custom mode
    deliberately remains legacy-authoritative because its operator-defined delta and
    time contract is separate from the Pb recovery recipes.
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
        self._v2_authoritative = (
            _env_bool("V2_AUTHORITATIVE", True)
            if authoritative is None
            else bool(authoritative)
        )

    @property
    def v2_authoritative(self) -> bool:
        return bool(self._v2_authoritative)

    def set_v2_authoritative(self, enabled: bool) -> None:
        """Runtime rollback switch; changing it never mutates the current stage."""
        self._v2_authoritative = bool(enabled)
        logger.warning("V2 actuator authority set to %s", self._v2_authoritative)

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
        if self.current_stage in (self.STAGE_IDLE, self.STAGE_DONE):
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

    def start(self, battery_type: str, ah_capacity: int) -> None:
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

    def try_restore_session(
        self,
        voltage: float,
        current: float,
        ah: float,
    ) -> Tuple[bool, Optional[str]]:
        trace_document = self._read_legacy_session_document()
        ok, message = super().try_restore_session(voltage, current, ah)
        if ok:
            self._restore_trace_identity(trace_document)
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
        transition_audit: Optional[LegacyTransitionAudit] = None,
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
        if transition_audit is not None:
            payload["transition_audit"] = self._transition_audit_metadata(transition_audit)
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
                chemistry_for_legacy_profile(self.battery_type),
                float(self.ah_capacity),
            )
            near_target = float(voltage) >= float(target_before) - 0.20
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
            self._v2_main_plateau_since = max(0.0, float(timestamp_s) - 15 * 60)
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

    @staticmethod
    def _log_transition_audit(audit: Optional[LegacyTransitionAudit]) -> None:
        if audit is None:
            return
        log_fn = logger.warning if audit.severity in {
            TransitionAuditSeverity.REVIEW,
            TransitionAuditSeverity.SAFETY,
        } else logger.info
        log_fn(
            "RECOVERY_TRANSITION_AUDIT severity=%s code=%s from=%s to=%s first_stage=%s reason=%s",
            audit.severity.value,
            audit.code,
            audit.stage_before,
            audit.stage_after,
            audit.first_stage_state.value if audit.first_stage_state is not None else "none",
            audit.reason,
        )

    def _is_authoritative_stage(self, stage: str) -> bool:
        return (
            self._v2_authoritative
            and self.battery_type != self.PROFILE_CUSTOM
            and stage in {self.STAGE_MAIN, self.STAGE_MIX}
        )

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
        """Run legacy common safety while masking its Main/Mix transition triggers."""
        if not self._is_authoritative_stage(stage_before):
            return await super().tick(
                voltage,
                current,
                temp_ext,
                is_cv,
                ah,
                output_is_on,
                manual_off_active=manual_off_active,
                is_cc=is_cc,
            )

        saved_blanking = self._blanking_until
        saved_delta_after = self._delta_monitor_after
        saved_stage_start = self.stage_start_time
        saved_finish_timer = self.finish_timer_start
        far_future = time.time() + 365 * 24 * 3600

        # In Main all Pb transition checks are guarded by blanking, while the hard
        # 72h safety timeout remains active. In Mix we additionally hide elapsed and
        # finish timer so profile/delta completion cannot fire in the legacy layer.
        self._blanking_until = far_future
        if stage_before == self.STAGE_MIX:
            self._delta_monitor_after = far_future
            self.stage_start_time = time.time()
            self.finish_timer_start = None

        try:
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
        finally:
            # A safety transition (Cooling/Done/Idle) owns its new timestamps/state.
            # Restore only if the scaffold left us in the stage it was asked to mask.
            if self.current_stage == stage_before:
                self._blanking_until = saved_blanking
                if stage_before == self.STAGE_MIX:
                    self._delta_monitor_after = saved_delta_after
                    self.stage_start_time = saved_stage_start
                    self.finish_timer_start = saved_finish_timer
        return actions

    def _mix_limit_seconds(self) -> float:
        if self.battery_type == self.PROFILE_AGM:
            return float(AGM_MIX_MAX_HOURS) * 3600.0
        if self.battery_type == self.PROFILE_EFB:
            return float(EFB_MIX_MAX_HOURS) * 3600.0
        return float(CA_MIX_MAX_HOURS) * 3600.0

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
        threshold = uv - SAFE_WAIT_V_MARGIN
        self.current_stage = self.STAGE_SAFE_WAIT
        self._clear_restored_targets()
        self.stage_start_time = now
        self._stage_start_ah = ah
        self._safe_wait_next_stage = self.STAGE_DONE
        self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
        self._safe_wait_start = now
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
        self._clear_session_file()
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
        self._agm_stage_idx = min(self._agm_stage_idx + 1, len(AGM_STAGES) - 1)
        self.stage_start_time = now
        self._stage_start_ah = ah
        self._reset_delta_and_blanking(now)
        self._v2_main_plateau_since = None
        uv, ui = self._main_target(temp)
        actions["set_voltage"] = uv
        actions["set_current"] = ui
        self._add_phase_limits(actions, uv, ui)
        actions["notify"] = (
            f"<b>🚀 V2 AGM ступень {self._agm_stage_idx + 1}/{len(AGM_STAGES)}:</b> "
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
    ) -> Optional[AuthorityDecision]:
        if not self._is_authoritative_stage(stage_before) or self.current_stage != stage_before:
            return None

        if stage_before == self.STAGE_MAIN:
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
            decision = decide_main_transition(
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
            policy_decision=record.decision.decision,
            mix_elapsed_s=max(0.0, timestamp_s - self.stage_start_time),
            mix_limit_s=self._mix_limit_seconds(),
            finish_hold_started_at=self.finish_timer_start,
            now_s=timestamp_s,
            finish_hold_s=MIX_DONE_TIMER,
        )
        if decision.action == AuthorityAction.START_FINISH_HOLD:
            self.finish_timer_start = timestamp_s
            self._delta_reported = True
            self._delta_trigger_mode = "CC" if is_cc else ("CV" if is_cv else None)
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
        stage_before = self.current_stage
        target_before = self._v2_target_voltage_v
        if target_before is None and stage_before not in {self.STAGE_IDLE, self.STAGE_SAFE_WAIT, self.STAGE_COOLING}:
            try:
                target_before = float(self._get_target_v_i(temp_ext)[0])
            except Exception:
                target_before = None

        actions = await self._run_legacy_scaffold_tick(
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

        timestamp_s = self.last_update_time or time.time()
        resolved_is_cc = bool(is_cc) if is_cc is not None else not bool(is_cv)
        authority_decision: Optional[AuthorityDecision] = None
        first_stage: Optional[FirstStageAssessment] = None
        transition_audit: Optional[LegacyTransitionAudit] = None
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
                    )
            else:
                self._log_shadow_disagreement(record, stage=stage_before)
                transition_audit = audit_legacy_transition(
                    stage_before=stage_before,
                    stage_after=self.current_stage,
                    first_stage=first_stage,
                )
                self._log_transition_audit(transition_audit)

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
                transition_audit=transition_audit,
                authority_decision=authority_decision,
            )
        except Exception as exc:
            # In legacy-fallback mode evidence remains diagnostic-only. In V2 authority
            # mode a failed evidence path must fail closed instead of silently handing
            # transition control back to legacy and possibly escalating voltage.
            logger.exception("RECOVERY_V2 observation/authority failed")
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
        if self._v2_runtime is not None and self._v2_runtime.records:
            last = self._v2_runtime.records[-1]
            m = last.analysis.metrics
            decision = last.decision.decision.value
            reason = last.decision.reason
            events = sorted(event.value for event in last.analysis.events)
            metrics = {
                "d_voltage_v_per_min": m.d_voltage_v_per_min,
                "d_current_a_per_min": m.d_current_a_per_min,
                "d_temp_c_per_min": m.d_temp_c_per_min,
                "current_min_a": m.current_min_a,
                "seconds_since_current_min": m.seconds_since_current_min,
                "delta_current_from_min_a": m.delta_current_from_min_a,
                "reversal_threshold_a": m.reversal_threshold_a,
                "voltage_max_v": m.voltage_max_v,
                "seconds_since_voltage_max": m.seconds_since_voltage_max,
                "delta_voltage_from_max_v": m.delta_voltage_from_max_v,
                "voltage_reversal_threshold_v": m.voltage_reversal_threshold_v,
            }
        return {
            "authoritative": self._v2_authoritative,
            "battery_id": self._v2_battery_id,
            "intent": self._v2_intent.value,
            "condition": self._v2_condition_before.value,
            "stage": self.current_stage,
            "is_cv": bool(self.is_cv),
            "is_cc": bool(self.is_cc),
            "finish_hold_started_at": self.finish_timer_start,
            "decision": decision,
            "reason": reason,
            "events": events,
            "metrics": metrics,
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
