#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "charge_logic.py"
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    text = text.replace(old, new, 1)


replace_once(
    'from config import MAX_VOLTAGE\nfrom charging_log import log_session_header\n',
    'from config import MAX_VOLTAGE\nfrom charging_log import log_session_header\nfrom legacy_safety import clamp_legacy_target_voltage, main_timeout_decision\n',
    "legacy safety import",
)

replace_once(
    '''    def _apply_temperature_compensation(self, base_v: float, temp_c: Optional[float]) -> float:\n        """Коррекция напряжения по температуре АКБ без изменения логики этапа."""\n        return round(max(0.0, base_v + self._temperature_compensation_delta(temp_c)), 2)\n''',
    '''    def _apply_temperature_compensation(self, base_v: float, temp_c: Optional[float]) -> float:\n        """Коррекция напряжения по температуре АКБ с финальным legacy safety ceiling."""\n        compensated = base_v + self._temperature_compensation_delta(temp_c)\n        return clamp_legacy_target_voltage(compensated)\n''',
    "temperature compensation clamp",
)

replace_once(
    '''        target_finish = data.get("target_finish_time")\n        target_v = float(data.get("target_voltage", 14.7))\n        target_i = float(data.get("target_current", 1.0))\n        target_i = min(MAX_STAGE_CURRENT, max(0.1, target_i))\n        self._restored_target_v = target_v\n''',
    '''        target_finish = data.get("target_finish_time")\n        target_v_raw = float(data.get("target_voltage", 14.7))\n        target_v = clamp_legacy_target_voltage(target_v_raw)\n        if abs(target_v - target_v_raw) >= 0.01:\n            logger.warning("Restore: target voltage clamped %.2fV -> %.2fV", target_v_raw, target_v)\n        target_i = float(data.get("target_current", 1.0))\n        target_i = min(MAX_STAGE_CURRENT, max(0.1, target_i))\n        self._restored_target_v = target_v\n''',
    "restore target clamp",
)

main_old = '''            # Защитный лимит времени MAIN (72ч авто, пользовательский для CUSTOM)\n            # При заданном условии «off» таймер режима не срабатывает — выключение только по off.\n            stage_elapsed_hours = (now - self.stage_start_time) / 3600.0\n            max_hours = self._custom_time_limit_hours if self.battery_type == self.PROFILE_CUSTOM else MAIN_STAGE_MAX_HOURS\n            if not manual_off_active and stage_elapsed_hours >= max_hours:\n                prev = self.current_stage\n                transition_threshold = DESULF_CURRENT_STUCK_AGM if self.battery_type == self.PROFILE_AGM else DESULF_CURRENT_STUCK\n                force_mix_on_timeout = self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB)\n                can_mix_by_threshold = self.battery_type != self.PROFILE_CUSTOM and is_cv and current <= transition_threshold\n                if force_mix_on_timeout or can_mix_by_threshold:\n                    timeout_reason = (\n                        f"Лимит {max_hours}ч, принудительный переход в MIX для {self.battery_type}"\n                        if force_mix_on_timeout\n                        else f"Лимит {max_hours}ч, I<={transition_threshold}A"\n                    )\n                    actions["log_event_end"] = self._make_log_event_end(\n                        now, ah, voltage, current, temp, timeout_reason\n                    )\n                    self.current_stage = self.STAGE_MIX\n                    self._clear_restored_targets()\n                    self.stage_start_time = now\n                    self._stage_start_ah = ah\n                    self._reset_delta_and_blanking(now)\n                    if force_mix_on_timeout:\n                        _log_trigger(prev, self.current_stage, "TIME_LIMIT_MAIN_TO_MIX_FORCE", f"Limit {max_hours}h reached for {self.battery_type}, forced MIX")\n                    else:\n                        _log_trigger(prev, self.current_stage, "TIME_LIMIT_MAIN_TO_MIX", f"Limit {max_hours}h, I={current:.2f}A <= {transition_threshold}A")\n                    mxv, mxi = self._mix_target(temp)\n                    actions["set_voltage"] = mxv\n                    actions["set_current"] = mxi\n                    self._add_phase_limits(actions, mxv, mxi)\n                    if force_mix_on_timeout:\n                        actions["notify"] = (\n                            f"<b>⏱ Лимит {max_hours}ч MAIN.</b> "\n                            "<b>Переход к:</b> Mix Mode по правилу тайм-лимита профиля."\n                        )\n                    else:\n                        actions["notify"] = (\n                            f"<b>⏱ Лимит {max_hours}ч MAIN.</b> Ток перехода достиг (I≤{transition_threshold}А). "\n                            "<b>Переход к:</b> Mix Mode."\n                        )\n                    actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"\n                else:\n                    actions["log_event_end"] = self._make_log_event_end(\n                        now, ah, voltage, current, temp, f"Лимит времени {max_hours}ч"\n                    )\n                    self.current_stage = self.STAGE_DONE\n                    self._clear_restored_targets()\n                    self.stage_start_time = now\n                    self._stage_start_ah = ah\n                    self._blanking_until = now + BLANKING_SEC\n                    self._delta_trigger_count = 0\n                    trigger_name = "TIME_LIMIT"\n                    condition = f"Достигнут лимит {max_hours}ч для этапа MAIN"\n                    _log_trigger(prev, self.current_stage, trigger_name, condition)\n                    actions["turn_off"] = True\n                    mode_text = "ручном режиме" if self.battery_type == self.PROFILE_CUSTOM else "автоматическом режиме"\n                    actions["notify"] = (\n                        "<b>🛑 ЛИМИТ ВРЕМЕНИ ДОСТИГНУТ!</b>\\n"\n                        f"Этап MAIN длился {stage_elapsed_hours:.1f}ч (лимит {max_hours}ч)\\n"\n                        f"Заряд в {mode_text} завершен. Проверьте состояние АКБ."\n                    )\n                    actions["log_event"] = "START"\n                    self._clear_session_file()\n                return actions\n'''
main_new = '''            # Защитный лимит MAIN — hard safety invariant. Пользовательское условие\n            # manual-off может завершить заряд раньше, но не имеет права отключать этот лимит.\n            stage_elapsed_hours = (now - self.stage_start_time) / 3600.0\n            max_hours = self._custom_time_limit_hours if self.battery_type == self.PROFILE_CUSTOM else MAIN_STAGE_MAX_HOURS\n            main_timeout = main_timeout_decision(elapsed_hours=stage_elapsed_hours, max_hours=max_hours)\n            if main_timeout.stop:\n                prev = self.current_stage\n                actions["log_event_end"] = self._make_log_event_end(\n                    now, ah, voltage, current, temp, main_timeout.reason\n                )\n                self.current_stage = self.STAGE_DONE\n                self._clear_restored_targets()\n                self.stage_start_time = now\n                self._stage_start_ah = ah\n                self._blanking_until = now + BLANKING_SEC\n                self._delta_trigger_count = 0\n                _log_trigger(prev, self.current_stage, "SAFETY_TIME_LIMIT_MAIN", main_timeout.reason)\n                actions["turn_off"] = True\n                mode_text = "ручном режиме" if self.battery_type == self.PROFILE_CUSTOM else "автоматическом режиме"\n                actions["notify"] = (\n                    "<b>🛑 ЗАЩИТНЫЙ ЛИМИТ MAIN ДОСТИГНУТ!</b>\\n"\n                    f"Этап MAIN длился {stage_elapsed_hours:.1f}ч (лимит {max_hours}ч).\\n"\n                    f"Заряд в {mode_text} остановлен без перехода на повышенное напряжение. "\n                    "Требуется диагностика АКБ."\n                )\n                actions["log_event"] = "START"\n                self._clear_session_file()\n                return actions\n'''
replace_once(main_old, main_new, "MAIN hard timeout")

for profile, label in (
    ("self.PROFILE_EFB", "EFB Mix timeout"),
    ("self.PROFILE_CA", "Ca/Ca Mix timeout"),
    ("self.PROFILE_AGM", "AGM Mix timeout"),
):
    old = f"elif not manual_off_active and self.battery_type == {profile} and elapsed >= "
    new = f"elif self.battery_type == {profile} and elapsed >= "
    replace_once(old, new, label)

PATH.write_text(text, encoding="utf-8")
print("Applied guarded P0 charge_logic safety migration")
