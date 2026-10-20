from __future__ import annotations

import time
from typing import Any, Dict, Optional

from production_controller import ProductionChargeController
from runtime.charge.strategy.mix_variables import mix_max_active_seconds


class AutoStrategyProductionChargeController(ProductionChargeController):
    """Production AUTO presentation/timer specialization over modular owners."""

    _OPERATOR_REASON_TEXT = {
        **ProductionChargeController._OPERATOR_REASON_TEXT,
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

    def _get_stage_max_hours(self) -> Optional[float]:
        if self.current_stage == self.STAGE_MIX and self.finish_timer_start is None:
            return mix_max_active_seconds(self.battery_type) / 3600.0
        return super()._get_stage_max_hours()

    def _mix_display_elapsed_s(self, now: float) -> float:
        authority = getattr(self, "_mix_active_authority", None)
        snapshot = getattr(authority, "snapshot", None)
        if snapshot is not None:
            try:
                if str(snapshot.session_id) == str(self.recovery_trace_context["session_id"]):
                    return max(0.0, float(snapshot.elapsed_s))
            except Exception:
                pass
        return max(0.0, float(now) - float(self.stage_start_time))

    def get_timers(self) -> Dict[str, Any]:
        timers = super().get_timers()
        if self.current_stage == self.STAGE_MIX and self.finish_timer_start is None:
            now = time.time()
            limit_s = mix_max_active_seconds(self.battery_type)
            elapsed = self._mix_display_elapsed_s(now)
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
            return "Main 14.7V; recovery budget 3/session; Mix max 20h active; normal finish -> SafeWait 2h."
        if self.battery_type == self.PROFILE_EFB:
            return "Main 14.8V; recovery budget 3/session; Mix max 24h active; normal finish -> SafeWait 2h."
        if self.battery_type == self.PROFILE_AGM:
            return "Main 14.4/14.6/14.8/15.0V; recovery budget 4/session; Mix max 10h active; normal finish -> SafeWait 2h."
        return super()._session_rules_summary()

    def get_ai_stage_snapshot(self, temp_c: Optional[float] = None) -> Dict[str, Any]:
        snapshot = super().get_ai_stage_snapshot(temp_c)
        if self.current_stage == self.STAGE_MIX and self.finish_timer_start is None:
            snapshot["mix_active_elapsed_s"] = self._mix_display_elapsed_s(time.time())
            snapshot["mix_timeout_semantics"] = "MIX_TIMEOUT -> Output OFF -> manual diagnosis"
        if (
            self.current_stage == self.STAGE_MIX
            and self.finish_timer_start is None
            and self.battery_type == self.PROFILE_EFB
        ):
            snapshot["summary"] = "Mix 16.5V / 0.03C: normal exit by ΔV/ΔI; 24h active-time authority ceiling."
            snapshot["transition"] = (
                "Normal exit by ΔV/ΔI; without delta, 24h active-time ceiling -> "
                "MIX_TIMEOUT, Output OFF, manual diagnosis."
            )
            policy = snapshot.get("mix_exit_policy")
            if isinstance(policy, dict):
                policy["fallback_limit_hours"] = 24.0
                policy["fallback_outcome"] = "MIX_TIMEOUT"
        return snapshot
