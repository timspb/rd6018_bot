from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Optional, Tuple

from charge_logic import AGM_FIRST_STAGE_HOLD_SEC, FIRST_STAGE_HOLD_SEC
from charge_controller_v2 import ChargeControllerV2
from first_stage_evidence import FirstStageAssessment, FirstStageState
from legacy_recipe_adapter import chemistry_for_legacy_profile
from pb_domain import BatteryCondition, BatteryIdentity, ChargeContext, ChargeIntent
from recipe_engine import RecipeEnvelope, select_recipe_envelope


class ProductionChargeControllerV2(ChargeControllerV2):
    """Live controller with recipe envelopes enforced at target generation."""

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
        "main_plateau_too_high_for_automatic_hv_escalation": (
            "Ток на полке слишком высок для безопасного автоматического HV-перехода."
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
        current_limit = (
            envelope.hv_current_limit_a if hv else envelope.main_current_limit_a
        )
        return (
            min(voltage_v, float(envelope.voltage_ceiling_v)),
            min(current_a, float(current_limit)),
        )

    def _current_stage_is_hv(self) -> bool:
        return self.current_stage in {self.STAGE_DESULFATION, self.STAGE_MIX}

    def _prep_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._prep_target(temp_c),
            self._recipe_envelope(),
            hv=False,
        )

    def _main_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._main_target(temp_c),
            self._recipe_envelope(),
            hv=False,
        )

    def _desulf_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._desulf_target(temp_c),
            self._recipe_envelope(),
            hv=True,
        )

    def _mix_target(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._mix_target(temp_c),
            self._recipe_envelope(),
            hv=True,
        )

    def _get_target_v_i(self, temp_c: Optional[float] = None) -> Tuple[float, float]:
        return self._bound_target(
            super()._get_target_v_i(temp_c),
            self._recipe_envelope(),
            hv=self._current_stage_is_hv(),
        )

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

    @classmethod
    def _operatorize_notification(cls, text: str) -> str:
        """Keep machine reason codes in trace/logs, never in operator Telegram text."""
        result = str(text or "")
        for reason, human in cls._OPERATOR_REASON_TEXT.items():
            result = result.replace(reason, human)
        replacements = {
            "<b>🚀 V2 → Mix Mode</b>": "<b>🚀 Переход в Mix</b>",
            "<b>🎯 V2 Delta подтверждена</b>": "<b>🎯 Delta подтверждена</b>",
            "<b>✅ V2: этап завершён.</b>": "<b>✅ Этап завершён.</b>",
            "<b>🛑 V2 остановил автоматическую эскалацию.</b>": (
                "<b>🛑 Автоматический переход остановлен.</b>"
            ),
            "<b>🚀 V2 AGM ступень": "<b>🚀 AGM ступень",
            "🔧 <b>V2 десульфатация": "🔧 <b>Десульфатация",
            "Sticky finish-hold: 2ч.": "Контрольная выдержка: 2 ч.",
        }
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result

    async def tick(self, *args, **kwargs):
        """Run managed V2 without legacy chatter and developer-facing Telegram text."""
        if self.is_active and self.battery_type != self.PROFILE_CUSTOM:
            self._last_hourly_report = time.time()
        actions = await super().tick(*args, **kwargs)
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

        # Never reconstruct continuous tail residence from the age of a persisted Imin.
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

        return ok, message
