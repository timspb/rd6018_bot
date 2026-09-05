from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

from charge_logic import AGM_FIRST_STAGE_HOLD_SEC, FIRST_STAGE_HOLD_SEC, SESSION_FILE
from charge_controller_v2 import ChargeControllerV2
from cooling_runtime import CoolingAwareShadowRecoveryRuntime
from first_stage_evidence import FirstStageAssessment, FirstStageState
from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryCondition, BatteryIdentity, ChargeContext, ChargeIntent
from recipe_engine import RecipeEnvelope, select_recipe_envelope


V2_MIX_MAX_HOURS = {
    "Ca/Ca": 20.0,
    "EFB": 24.0,
    "AGM": 10.0,
}


class ProductionChargeControllerV2(ChargeControllerV2):
    """Live controller with recipe envelopes and production pause semantics."""

    _OPERATOR_REASON_TEXT = {
        "main_tail_hold_complete_recovery_hv_authorized": (
            "Хвост основного заряда стабилен; восстановительный HV-этап разрешён."
        ),
        "main_tail_hold_complete_normal_charge": (
            "Хвост основного заряда стабилен; основной заряд завершён."
        ),
        "moderate_stable_cv_plateau_recovery_evidence": (
            "Подтверждена стабильная CV-полка; разрешён сервисный этап восстановления."
        ),
        "moderate_plateau_after_desulfation_budget": (
            "CV-полка сохраняется после допустимых сервисных попыток; переход в Mix."
        ),
        "agm_tail_hold_complete_advance_voltage_step": (
            "AGM-хвост стабилен; переход на следующую ступень напряжения."
        ),
        "persistent_main_plateau_requires_recovery_intent": (
            "Устойчивая полка требует отдельного режима восстановления."
        ),
        "confirmed_delta_finish_hold_complete": (
            "Подтверждённая Delta выдержана 2 часа; активный этап завершён."
        ),
        "mix_profile_observation_window_exhausted": (
            "Достигнут максимальный безопасный интервал наблюдения Mix."
        ),
        "mode_specific_end_of_charge_evidence_confirmed": (
            "Подтверждён признак окончания заряда; запущена двухчасовая контрольная выдержка."
        ),
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._v2_continuous_tail_since: Optional[float] = None
        self._v2_continuous_tail_stage_start: Optional[float] = None
        self._v2_cooling_pause: Optional[Dict[str, Any]] = None

    def _new_runtime(self, *, started_at: float) -> CoolingAwareShadowRecoveryRuntime:
        battery_id = self._v2_battery_id or (
            f"session:{self.battery_type}:{self.ah_capacity}:{int(started_at)}"
        )
        runtime = CoolingAwareShadowRecoveryRuntime(
            battery_id=battery_id,
            started_at=started_at,
            intent=self._v2_intent,
            condition_before=self._v2_condition_before,
        )
        self._v2_runtime = runtime
        return runtime

    def _recipe_envelope(self) -> Optional[RecipeEnvelope]:
        if self.battery_type == self.PROFILE_CUSTOM:
            return None
        chemistry = chemistry_for_legacy_profile(self.battery_type)
        identity = BatteryIdentity(
            battery_id=self._v2_battery_id or f"runtime:{self.battery_type}",
            chemistry=chemistry,
            nominal_capacity_ah=float(max(1, self.ah_capacity)),
        )
        return select_recipe_envelope(
            ChargeContext(
                identity=identity,
                intent=self._v2_intent,
                condition=self._v2_condition_before,
            ),
            expert_high_voltage=False,
        )

    @staticmethod
    def _bound_target(
        target: Tuple[float, float],
        envelope: Optional[RecipeEnvelope],
        *,
        hv: bool,
    ) -> Tuple[float, float]:
        if envelope is None:
            return target
        voltage_v, current_a = float(target[0]), float(target[1])
        current_limit = envelope.hv_current_limit_a if hv else envelope.main_current_limit_a
        return (
            min(voltage_v, float(envelope.voltage_ceiling_v)),
            min(current_a, float(current_limit)),
        )

    def _current_stage_is_hv(self) -> bool:
        return self.current_stage in {self.STAGE_DESULFATION, self.STAGE_MIX}

    def _prep_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(super()._prep_target(temp_c), self._recipe_envelope(), hv=False)

    def _main_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(super()._main_target(temp_c), self._recipe_envelope(), hv=False)

    def _desulf_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(super()._desulf_target(temp_c), self._recipe_envelope(), hv=True)

    def _mix_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(super()._mix_target(temp_c), self._recipe_envelope(), hv=True)

    def _get_target_v_i(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._get_target_v_i(temp_c),
            self._recipe_envelope(),
            hv=self._current_stage_is_hv(),
        )

    def _mix_limit_seconds(self) -> float:
        return float(V2_MIX_MAX_HOURS.get(self.battery_type, 20.0)) * 3600.0

    def _continuous_tail_hold_seconds(self) -> float:
        return float(
            AGM_FIRST_STAGE_HOLD_SEC
            if self.battery_type == self.PROFILE_AGM
            else FIRST_STAGE_HOLD_SEC
        )

    def _reset_continuous_tail_hold(self) -> None:
        self._v2_continuous_tail_since = None
        self._v2_continuous_tail_stage_start = None

    def _assess_main_sample(self, **kwargs: Any) -> Optional[FirstStageAssessment]:
        """Require an uninterrupted TAIL_READY residence before production authority."""
        assessment = super()._assess_main_sample(**kwargs)
        stage_before = kwargs.get("stage_before")
        if stage_before != self.STAGE_MAIN or assessment is None:
            self._reset_continuous_tail_hold()
            return assessment

        timestamp_s = float(kwargs.get("timestamp_s") or 0.0)
        stage_marker = float(self.stage_start_time or 0.0)
        if self._v2_continuous_tail_stage_start != stage_marker:
            self._v2_continuous_tail_stage_start = stage_marker
            self._v2_continuous_tail_since = None

        if assessment.state != FirstStageState.TAIL_READY:
            self._v2_continuous_tail_since = None
            return assessment

        if self._v2_continuous_tail_since is None:
            self._v2_continuous_tail_since = timestamp_s

        held_s = max(0.0, timestamp_s - self._v2_continuous_tail_since)
        required_s = self._continuous_tail_hold_seconds()
        if held_s + 1e-6 >= required_s:
            return assessment

        return replace(
            assessment,
            state=FirstStageState.BULK_OR_TAPER,
            reason=(
                f"continuous tail hold {held_s / 3600.0:.2f}h / "
                f"{required_s / 3600.0:.2f}h"
            ),
        )

    @staticmethod
    def _tick_arg(args: tuple[Any, ...], kwargs: Dict[str, Any], name: str, index: int, default: Any = None) -> Any:
        if name in kwargs:
            return kwargs[name]
        return args[index] if len(args) > index else default

    def _runtime_signal_snapshot(self) -> Dict[str, Any]:
        runtime = self._v2_runtime
        if not isinstance(runtime, CoolingAwareShadowRecoveryRuntime):
            return {}
        tracker = runtime.tracker
        analyzer = tracker._analyzer
        return {
            "tracker_stage_key": tracker._stage_key,
            "tracker_stage_started_at": tracker._stage_started_at,
            "tracker_stage_start_ah": tracker._stage_start_ah,
            "analyzer_stage_name": analyzer.stage_name,
            "analyzer_target_voltage_v": analyzer.target_voltage_v,
            "current_min_a": analyzer._current_min_a,
            "current_min_time_s": analyzer._current_min_time_s,
            "voltage_max_v": analyzer._voltage_max_v,
            "voltage_max_time_s": analyzer._voltage_max_time_s,
            "reversal_emitted": analyzer._reversal_emitted,
            "voltage_reversal_emitted": analyzer._voltage_reversal_emitted,
        }

    def _restore_runtime_signal_snapshot(self, state: Dict[str, Any]) -> None:
        runtime = self._v2_runtime
        if not isinstance(runtime, CoolingAwareShadowRecoveryRuntime) or not state:
            return
        tracker = runtime.tracker
        analyzer = tracker._analyzer
        tracker._stage_key = state.get("tracker_stage_key")
        tracker._stage_started_at = state.get("tracker_stage_started_at")
        tracker._stage_start_ah = state.get("tracker_stage_start_ah")
        analyzer.reset_stage(
            state.get("analyzer_stage_name"),
            target_voltage_v=state.get("analyzer_target_voltage_v"),
        )
        analyzer._current_min_a = state.get("current_min_a")
        analyzer._current_min_time_s = state.get("current_min_time_s")
        analyzer._voltage_max_v = state.get("voltage_max_v")
        analyzer._voltage_max_time_s = state.get("voltage_max_time_s")
        analyzer._reversal_emitted = bool(state.get("reversal_emitted", False))
        analyzer._voltage_reversal_emitted = bool(state.get("voltage_reversal_emitted", False))

    def _capture_cooling_pause(
        self,
        *,
        entered_at: float,
        source_stage: str,
        source_stage_start_time: float,
        source_stage_start_ah: float,
        source_target: Tuple[float, float],
        source_finish_timer_start: Optional[float],
        source_first_hold_since: Optional[float],
        source_first_hold_current: Optional[float],
        source_cv_since: Optional[float],
        source_tail_since: Optional[float],
        source_runtime_signal: Dict[str, Any],
    ) -> None:
        self._v2_cooling_pause = {
            "source_stage": source_stage,
            "entered_at": float(entered_at),
            "source_stage_start_time": float(source_stage_start_time),
            "source_stage_start_ah": float(source_stage_start_ah),
            "target_v": float(source_target[0]),
            "target_i": float(source_target[1]),
            "finish_timer_start": source_finish_timer_start,
            "first_stage_hold_since": source_first_hold_since,
            "first_stage_hold_current": source_first_hold_current,
            "cv_since": source_cv_since,
            "continuous_tail_since": source_tail_since,
            "delta_reported": bool(self._delta_reported),
            "delta_trigger_mode": self._delta_trigger_mode,
            "runtime_signal": source_runtime_signal,
        }
        # Always return to the exact target that was active before Cooling. This also
        # fixes legacy PREP -> Cooling, where _get_current_targets() returned 14V/1A.
        self._cooling_from_stage = source_stage
        self._cooling_target_v, self._cooling_target_i = source_target
        self.finish_timer_start = source_finish_timer_start
        self._stuck_current_since = None
        self._stuck_current_value = None
        self._v2_main_plateau_since = None
        self._delta_trigger_count = 0
        self._last_delta_confirm_time = 0.0

    def _resume_cooling_pause(self, *, resumed_at: float) -> None:
        pause = self._v2_cooling_pause
        if not pause:
            return
        duration = max(0.0, float(resumed_at) - float(pause["entered_at"]))
        self.stage_start_time = float(pause["source_stage_start_time"]) + duration
        self._stage_start_ah = float(pause.get("source_stage_start_ah") or self._stage_start_ah)

        finish = pause.get("finish_timer_start")
        self.finish_timer_start = float(finish) + duration if finish is not None else None
        hold_since = pause.get("first_stage_hold_since")
        self._first_stage_hold_since = float(hold_since) + duration if hold_since is not None else None
        self._first_stage_hold_current = pause.get("first_stage_hold_current")
        cv_since = pause.get("cv_since")
        self._cv_since = float(cv_since) + duration if cv_since is not None else None
        tail_since = pause.get("continuous_tail_since")
        self._v2_continuous_tail_since = float(tail_since) + duration if tail_since is not None else None
        self._v2_continuous_tail_stage_start = self.stage_start_time

        self._stuck_current_since = None
        self._stuck_current_value = None
        self._v2_main_plateau_since = None
        self._delta_trigger_count = 0
        self._last_delta_confirm_time = 0.0
        self._delta_reported = bool(pause.get("delta_reported", False))
        self._delta_trigger_mode = pause.get("delta_trigger_mode")

        runtime = self._v2_runtime
        if isinstance(runtime, CoolingAwareShadowRecoveryRuntime):
            # A fresh process restore reconstructs the pre-Cooling extrema first.
            self._restore_runtime_signal_snapshot(dict(pause.get("runtime_signal") or {}))
            runtime.resume_after_cooling(duration)

        self._v2_cooling_pause = None

    def _write_cooling_pause_to_session_file(self) -> None:
        document = self._read_legacy_session_document()
        if not document:
            return
        if self._v2_cooling_pause is not None:
            document["v2_cooling_pause"] = self._v2_cooling_pause
        else:
            document.pop("v2_cooling_pause", None)
        tmp_path = f"{SESSION_FILE}.cooling.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, SESSION_FILE)
        except OSError:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _save_session(self, voltage: float, current: float, ah: float) -> None:
        super()._save_session(voltage, current, ah)
        self._write_cooling_pause_to_session_file()

    @classmethod
    def _operatorize_notification(cls, text: str) -> str:
        result = str(text or "")
        for reason, human in cls._OPERATOR_REASON_TEXT.items():
            result = result.replace(reason, human)
        replacements = {
            "<b>🚀 V2 → Mix Mode</b>": "<b>🚀 Переход в Mix</b>",
            "<b>🎯 V2 Delta подтверждена</b>": "<b>🎯 Delta подтверждена</b>",
            "<b>✅ V2: этап завершён.</b>": "<b>✅ Этап завершён.</b>",
            "<b>🛑 V2 остановил автоматическую эскалацию.</b>": "<b>🛑 Автоматический переход остановлен.</b>",
            "<b>🚀 V2 AGM ступень": "<b>🚀 AGM ступень",
            "🔧 <b>V2 десульфатация": "🔧 <b>Десульфатация",
            "Sticky finish-hold: 2ч.": "Контрольная выдержка: 2 ч.",
        }
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result

    async def tick(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Run managed V2 and enforce Cooling as a true pause of charge evidence."""
        if self.is_active and self.battery_type != self.PROFILE_CUSTOM:
            self._last_hourly_report = time.time()

        stage_before = self.current_stage
        temp_ext = self._tick_arg(args, kwargs, "temp_ext", 2)
        voltage = self._tick_arg(args, kwargs, "voltage", 0, 0.0)
        current = self._tick_arg(args, kwargs, "current", 1, 0.0)
        ah = self._tick_arg(args, kwargs, "ah", 4, 0.0)

        pre_stage_start = float(self.stage_start_time or 0.0)
        pre_stage_start_ah = float(self._stage_start_ah or 0.0)
        pre_finish = self.finish_timer_start
        pre_hold_since = self._first_stage_hold_since
        pre_hold_current = self._first_stage_hold_current
        pre_cv_since = self._cv_since
        pre_tail_since = self._v2_continuous_tail_since
        pre_runtime_signal = self._runtime_signal_snapshot()
        try:
            pre_target = tuple(float(v) for v in self._get_target_v_i(temp_ext))
        except Exception:
            pre_target = (float(self._cooling_target_v or 0.0), float(self._cooling_target_i or 0.0))

        actions = await super().tick(*args, **kwargs)
        now = float(self.last_update_time or time.time())

        if stage_before != self.STAGE_COOLING and self.current_stage == self.STAGE_COOLING:
            self._capture_cooling_pause(
                entered_at=now,
                source_stage=stage_before,
                source_stage_start_time=pre_stage_start,
                source_stage_start_ah=pre_stage_start_ah,
                source_target=pre_target,
                source_finish_timer_start=pre_finish,
                source_first_hold_since=pre_hold_since,
                source_first_hold_current=pre_hold_current,
                source_cv_since=pre_cv_since,
                source_tail_since=pre_tail_since,
                source_runtime_signal=pre_runtime_signal,
            )
            self._save_session(float(voltage), float(current), float(ah))
        elif stage_before == self.STAGE_COOLING and self.current_stage != self.STAGE_COOLING:
            self._resume_cooling_pause(resumed_at=now)
            self._save_session(float(voltage), float(current), float(ah))

        if isinstance(actions.get("notify"), str):
            actions["notify"] = self._operatorize_notification(actions["notify"])
        return actions

    def try_restore_session(
        self,
        voltage: float,
        current: float,
        ah: float,
    ) -> Tuple[bool, Optional[str]]:
        """Restore V2 sessions without granting recovery authority to legacy files."""
        document = self._read_legacy_session_document()
        ok, message = super().try_restore_session(voltage, current, ah)
        if not ok:
            return ok, message

        self._reset_continuous_tail_hold()

        if not document.get("v2_intent"):
            self._v2_intent = ChargeIntent.NORMAL
            self._v2_condition_before = BatteryCondition.UNKNOWN
            self._initialize_shadow_session(started_at=self._v2_trace_started_at)
            self._write_trace_identity_to_session_file()

        if self._restored_target_v > 0 and self._restored_target_i > 0:
            bounded_v, bounded_i = self._bound_target(
                (self._restored_target_v, self._restored_target_i),
                self._recipe_envelope(),
                hv=self._current_stage_is_hv(),
            )
            self._restored_target_v = bounded_v
            self._restored_target_i = bounded_i

        pause = document.get("v2_cooling_pause")
        if self.current_stage == self.STAGE_COOLING and isinstance(pause, dict):
            self._v2_cooling_pause = dict(pause)
            self._cooling_from_stage = str(pause.get("source_stage") or self.STAGE_MAIN)
            self._cooling_target_v = float(pause.get("target_v") or 0.0)
            self._cooling_target_i = float(pause.get("target_i") or 0.0)
            self.finish_timer_start = pause.get("finish_timer_start")
            self._delta_reported = bool(pause.get("delta_reported", False))
            self._delta_trigger_mode = pause.get("delta_trigger_mode")
            self._restore_runtime_signal_snapshot(dict(pause.get("runtime_signal") or {}))
            self._v2_target_voltage_v = self._cooling_target_v or self._v2_target_voltage_v

        return ok, message
