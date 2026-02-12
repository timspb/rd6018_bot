"""
charge_logic.py — State Machine заряда для Ca/Ca, EFB, AGM.
Профили: Ca/Ca (Liquid), EFB, AGM с десульфатацией и Mix Mode.
Auto-Resume: сохранение сессии в charge_session.json, восстановление при перезапуске.
"""
import json
import logging
import math
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import MAX_VOLTAGE

logger = logging.getLogger("rd6018")

SESSION_FILE = "charge_session.json"
SESSION_MAX_AGE = 60 * 60  # сек — восстанавливать только если последняя запись < 60 мин назад
SESSION_START_MAX_AGE = 24 * 60 * 60  # сек — если start_time старше 24 ч или 0, принудительно now()

# Пороги детекции
DELTA_V_EXIT = 0.03  # В — выход CC при падении V от пика
DELTA_I_EXIT = 0.03  # А — выход CV при росте I от минимума
TEMP_RISE_LIMIT = 2.0  # °C за 5 мин
TEMP_RISE_WINDOW = 300  # сек (5 мин)
DESULF_CURRENT_STUCK = 0.3  # А — порог «застревания» для десульфации
DESULF_STUCK_MIN_MINUTES = 30  # мин — минимум времени застревания перед десульфацией
MIX_DONE_TIMER = 2 * 3600  # сек — таймер после delta до Done
EFB_MIX_MAX_HOURS = 10
AGM_STAGES = [14.4, 14.6, 14.8, 15.0]  # В — четырёхступенчатый подъём
AGM_STAGE_MIN_MINUTES = 15  # мин на каждой ступени перед переходом

# Безопасный переход HV -> LV
SAFE_WAIT_V_MARGIN = 0.5  # В — ждать падения до (цель - 0.5В)
SAFE_WAIT_MAX_SEC = 2 * 3600  # макс 2 часа ожидания
HIGH_V_FOR_SAFE_WAIT = 15.0  # переходы с V > 15В требуют ожидания
PHANTOM_CHARGE_MINUTES = 15  # мин — ток < 0.3А за это время = подозрительный заряд
BLANKING_SEC = 5 * 60  # сек — после смены фазы или включения выхода игнорировать триггеры
TRIGGER_CONFIRM_COUNT = 3  # подтверждений подряд с интервалом 1 мин для срабатывания Delta
TRIGGER_CONFIRM_INTERVAL_SEC = 60  # сек — интервал между замерами для подтверждения
MAIN_MIX_STUCK_CV_MIN = 40  # мин в CV с током >=0.3А перед MAIN->MIX (desulf limit) для Ca/EFB
ELAPSED_MAX_HOURS = 1000  # если elapsed > 1000 ч — ошибка времени, сброс start_time
TELEMETRY_HISTORY_MINUTES = 15  # для AI только последние 15 мин

# Hardware Watchdog
WATCHDOG_TIMEOUT = 5 * 60  # сек — нет данных 5 мин → аварийное отключение
HIGH_V_FAST_TIMEOUT = 60  # сек — при U>15В: нет данных 60 сек → немедленное отключение
HIGH_V_THRESHOLD = 15.0  # В — порог для ускоренного watchdog

# Активная безопасность: OVP/OCP, температурная защита (все режимы Ca/Ca, EFB, AGM)
OVP_OFFSET = 0.2  # В — OVP = целевое U + 0.2
OCP_OFFSET = 0.5  # А — OCP = лимит I + 0.5
TEMP_WARNING = 34.0  # °C — предупреждение в Telegram (один раз за сессию)
TEMP_EMERGENCY = 37.0  # °C — аварийное отключение, полный сброс


def _log_phase(phase: str, v: float, i: float, t: float) -> None:
    """Лог в консоль: Время | Фаза | V | I | T."""
    ts = datetime.now().strftime("%H:%M:%S")
    logger.info("%s | %-12s | %5.2fВ | %5.2fА | %5.1f°C", ts, phase, v, i, t)


def _log_trigger(from_stage: str, to_stage: str, reason: str) -> None:
    """Детальная причина смены этапа — в лог и консоль."""
    msg = f"[Триггер] Переход {from_stage} -> {to_stage}. Причина: {reason}"
    logger.info(msg)


class ChargeController:
    """
    Контроллер заряда с машиной состояний.
    Этапы: PОДГОТОВКА (Soft Start), Main (Bulk), Desulfation, Mix, Done.
    """

    STAGE_PREP = "Подготовка"
    STAGE_MAIN = "Main Charge"
    STAGE_DESULFATION = "Десульфатация"
    STAGE_ANTI_SULF = "Десульфатация"  # v2.5: алиас для ясности (16.3В/2%Ah на 2ч)
    STAGE_MIX = "Mix Mode"  # v2.5: 16.5В/3%Ah до 10ч для EFB
    STAGE_SAFE_WAIT = "Безопасное ожидание"
    STAGE_DONE = "Done"
    STAGE_IDLE = "Idle"

    PROFILE_CA = "Ca/Ca"
    PROFILE_EFB = "EFB"
    PROFILE_AGM = "AGM"

    def __init__(self, hass_client: Any, notify_cb: Optional[Callable[[str], Any]] = None) -> None:
        self.hass = hass_client
        self.notify = notify_cb or (lambda _: None)
        self.battery_type: str = self.PROFILE_CA
        self.ah_capacity: int = 60
        self.current_stage: str = self.STAGE_IDLE
        self.stage_start_time: float = 0.0
        self.antisulfate_count: int = 0
        self.v_max_recorded: Optional[float] = None
        self.i_min_recorded: Optional[float] = None
        self.finish_timer_start: Optional[float] = None
        self._phantom_alerted: bool = False
        self.temp_history: deque = deque(maxlen=20)
        self._last_log_time: float = 0.0
        self._agm_stage_idx: int = 0
        self._delta_reported: bool = False
        self.is_cv: bool = False
        self._stuck_current_since: Optional[float] = None  # когда ток впервые застрял > 0.3А в CV
        self.last_update_time: float = 0.0  # время последнего вызова tick() — для watchdog
        self.emergency_hv_disconnect: bool = False  # флаг после аварийного отключения при U>15В
        self._phase_current_limit: float = 0.0  # базовый лимит тока текущей фазы
        self._temp_34_alerted: bool = False  # предупреждение 34°C отправлено один раз за сессию
        self._pending_log_event: Optional[str] = None  # для логирования 34°C
        self._start_ah: float = 0.0  # накопленная ёмкость на старте сессии
        self._last_checkpoint_time: float = 0.0  # для контрольных точек каждые 10 мин
        self._last_save_time: float = 0.0
        self._safe_wait_next_stage: Optional[str] = None  # куда перейти после ожидания
        self._safe_wait_target_v: float = 0.0
        self._safe_wait_target_i: float = 0.0
        self._safe_wait_start: float = 0.0
        self._last_hourly_report: float = 0.0  # для прогресс-репортов раз в час
        self._analytics_history: deque = deque(maxlen=80)  # (ts, v, i, ah, temp) ~40 мин при 30с
        self._safe_wait_v_samples: deque = deque(maxlen=30)  # (ts, v) каждые 5 мин
        self._last_safe_wait_sample: float = 0.0
        self._blanking_until: float = 0.0  # до этого времени игнорировать триггеры после смены фазы
        self._delta_trigger_count: int = 0  # подряд выполнений условия Delta для подтверждения
        self._session_start_reason: str = "User Command"  # User Command | Auto-restore
        self._last_known_output_on: bool = False  # последнее известное состояние выхода (для EMERGENCY_UNAVAILABLE)
        self._was_unavailable: bool = False  # предыдущий тик был unavailable → при восстановлении попробовать restore
        # История замеров V/I за последние 20 мин, обновление раз в минуту
        self.v_history: deque = deque(maxlen=21)
        self.i_history: deque = deque(maxlen=21)
        self._last_v_i_history_time: float = 0.0
        self._last_delta_confirm_time: float = 0.0  # для подтверждения триггера раз в 1 мин
        self._cv_since: Optional[float] = None  # v2.5: время начала CV-режима для отслеживания 40 мин

    def _add_phase_limits(self, actions: Dict[str, Any], target_v: float, target_i: float) -> None:
        """Добавить OVP/OCP в actions при смене фазы."""
        actions["set_ovp"] = target_v + OVP_OFFSET
        actions["set_ocp"] = target_i + OCP_OFFSET
        self._phase_current_limit = target_i

    def start(self, battery_type: str, ah_capacity: int) -> None:
        """Запуск заряда по профилю."""
        self.battery_type = battery_type
        self.ah_capacity = max(1, ah_capacity)
        self.current_stage = self.STAGE_PREP
        self.stage_start_time = time.time()
        self.antisulfate_count = 0
        self.v_max_recorded = None
        self.i_min_recorded = None
        self.finish_timer_start = None
        self._phantom_alerted = False
        self.temp_history.clear()
        self._agm_stage_idx = 0
        self._delta_reported = False
        self._stuck_current_since = None
        self.emergency_hv_disconnect = False
        self._temp_34_alerted = False
        self._pending_log_event = None
        self._start_ah = 0.0
        self._last_checkpoint_time = 0.0
        self._safe_wait_next_stage = None
        self._safe_wait_target_v = 0.0
        self._safe_wait_target_i = 0.0
        self._safe_wait_start = 0.0
        self._last_hourly_report = 0.0
        self._analytics_history.clear()
        self._safe_wait_v_samples.clear()
        self._last_safe_wait_sample = 0.0
        self._blanking_until = 0.0
        self._delta_trigger_count = 0
        self._last_delta_confirm_time = 0.0
        self.v_history.clear()
        self.i_history.clear()
        self._last_v_i_history_time = 0.0
        self._cv_since = None
        self._session_start_reason = "User Command"
        self._clear_session_file()
        logger.info("ChargeController started: %s %dAh (%s)", battery_type, self.ah_capacity, self._session_start_reason)

    def stop(self, clear_session: bool = True) -> None:
        """Остановка заряда. Если clear_session=False, файл сессии не удаляется (для восстановления после связи)."""
        prev = self.current_stage
        self.current_stage = self.STAGE_IDLE
        self.v_max_recorded = None
        self.i_min_recorded = None
        if clear_session:
            self._clear_session_file()
        logger.info("ChargeController stopped (was: %s)", prev)

    def _clear_session_file(self) -> None:
        """Удалить файл сессии."""
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
        except OSError:
            pass

    def _get_target_finish_time(self) -> Optional[float]:
        """Время завершения текущей фазы (timestamp) или None."""
        if self.current_stage == self.STAGE_SAFE_WAIT:
            return self._safe_wait_start + SAFE_WAIT_MAX_SEC
        if self.current_stage == self.STAGE_DESULFATION:
            return self.stage_start_time + 2 * 3600
        if self.current_stage == self.STAGE_MIX:
            if self.finish_timer_start is not None:
                return self.finish_timer_start + MIX_DONE_TIMER
            if self.battery_type == self.PROFILE_EFB:
                return self.stage_start_time + EFB_MIX_MAX_HOURS * 3600
        return None

    def _get_target_v_i(self) -> Tuple[float, float]:
        """Текущие целевые V и I для фазы."""
        if self.current_stage == self.STAGE_PREP:
            return self._prep_target()
        if self.current_stage == self.STAGE_MAIN:
            return self._main_target()
        if self.current_stage == self.STAGE_DESULFATION:
            return self._desulf_target()
        if self.current_stage == self.STAGE_MIX:
            return self._mix_target()
        if self.current_stage == self.STAGE_SAFE_WAIT:
            return (0.0, 0.0)  # выход выключен
        if self.current_stage == self.STAGE_DONE:
            return self._storage_target()
        return (0.0, 0.0)

    def _save_session(self, voltage: float, current: float, ah: float) -> None:
        """Сохранить текущее состояние в charge_session.json."""
        if self.current_stage in (self.STAGE_IDLE, self.STAGE_DONE):
            return
        target_finish = self._get_target_finish_time()
        if self.current_stage == self.STAGE_SAFE_WAIT:
            uv, ui = self._safe_wait_target_v, self._safe_wait_target_i
        else:
            uv, ui = self._get_target_v_i()
        data = {
            "profile": self.battery_type,
            "stage": self.current_stage,
            "stage_start_time": self.stage_start_time,
            "target_finish_time": target_finish,
            "finish_timer_start": self.finish_timer_start,
            "ah_limit": self.ah_capacity,
            "start_ah": self._start_ah,
            "current_retries": self.antisulfate_count,
            "target_voltage": uv,
            "target_current": ui,
            "agm_stage_idx": self._agm_stage_idx,
            "safe_wait_next_stage": self._safe_wait_next_stage,
            "safe_wait_target_v": self._safe_wait_target_v,
            "safe_wait_target_i": self._safe_wait_target_i,
            "safe_wait_start": self._safe_wait_start,
            "saved_at": time.time(),
        }
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as ex:
            logger.warning("Could not save session: %s", ex)

    def try_restore_session(
        self, voltage: float, current: float, ah: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Восстановить сессию из файла, если прошло < 60 мин.
        Возвращает (ok, notify_message).
        """
        if not os.path.exists(SESSION_FILE):
            return False, None
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False, None

        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > SESSION_MAX_AGE:
            self._clear_session_file()
            return False, None

        self.battery_type = data.get("profile", self.PROFILE_CA)
        self.ah_capacity = int(data.get("ah_limit", 60))
        self.current_stage = data.get("stage", self.STAGE_MAIN)
        self.antisulfate_count = int(data.get("current_retries", 0))
        self._agm_stage_idx = int(data.get("agm_stage_idx", 0))
        self._start_ah = float(data.get("start_ah", 0))
        self._safe_wait_next_stage = data.get("safe_wait_next_stage")
        self._safe_wait_target_v = float(data.get("safe_wait_target_v", 0))
        self._safe_wait_target_i = float(data.get("safe_wait_target_i", 0))
        now = time.time()
        raw_safe_wait_start = data.get("safe_wait_start")
        try:
            self._safe_wait_start = float(raw_safe_wait_start) if raw_safe_wait_start not in (None, 0) else now
        except (TypeError, ValueError):
            self._safe_wait_start = now

        target_finish = data.get("target_finish_time")
        target_v = float(data.get("target_voltage", 14.7))
        target_i = float(data.get("target_current", 1.0))
        self.finish_timer_start = data.get("finish_timer_start")
        raw_stage_start = data.get("stage_start_time")
        try:
            saved_stage_start = float(raw_stage_start) if raw_stage_start not in (None, 0) else now
        except (TypeError, ValueError):
            saved_stage_start = now
        # Фикс "1970 года": если start_time отсутствует, 0 или старше 24 ч — принудительно now()
        if not saved_stage_start or saved_stage_start <= 0 or (now - saved_stage_start) > SESSION_START_MAX_AGE:
            saved_stage_start = now
            logger.info("Restore: start_time invalid or >24h, set to now()")

        self._session_start_reason = "Auto-restore"

        if target_finish is not None:
            remaining_sec = target_finish - now
            if remaining_sec > 0:
                if self.current_stage == self.STAGE_DESULFATION:
                    phase_dur = 2 * 3600
                    self.stage_start_time = now - (phase_dur - remaining_sec)
                elif self.current_stage == self.STAGE_MIX and self.finish_timer_start is not None:
                    self.finish_timer_start = target_finish - MIX_DONE_TIMER
                else:
                    if saved_stage_start and 0 < saved_stage_start <= now:
                        self.stage_start_time = saved_stage_start
                    else:
                        self.stage_start_time = now
                remaining_min = int(remaining_sec / 60)
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Продолжаю режим: <code>{self.current_stage}</code>.\n"
                    f"Осталось времени: <code>{remaining_min}</code> мин.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
            else:
                if self.current_stage == self.STAGE_DESULFATION:
                    self.current_stage = self.STAGE_MAIN
                    self.stage_start_time = now
                elif self.current_stage == self.STAGE_MIX and self.battery_type == self.PROFILE_EFB:
                    self.current_stage = self.STAGE_DONE
                    self.stage_start_time = now
                remaining_min = 0
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Переход к следующей фазе: <code>{self.current_stage}</code>.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
        else:
            remaining_min = 0
            self.stage_start_time = saved_stage_start if saved_stage_start and saved_stage_start <= now else now
            msg = (
                f"🔄 <b>Сессия восстановлена!</b>\n\n"
                f"Продолжаю режим: <code>{self.current_stage}</code>.\n"
                f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
            )

        self.v_max_recorded = None
        self.i_min_recorded = None
        self.finish_timer_start = None
        self._blanking_until = now + BLANKING_SEC
        self._delta_trigger_count = 0
        elapsed_sec = now - self.stage_start_time
        if elapsed_sec < 0 or elapsed_sec > ELAPSED_MAX_HOURS * 3600:
            self.stage_start_time = now
            logger.warning("Restore: stage_start_time corrected (elapsed invalid)")
        return True, msg

    def full_reset(self) -> None:
        """Полный сброс состояния (при аварийном отключении по температуре)."""
        self.stop()
        self.temp_history.clear()
        self._temp_34_alerted = False
        self.finish_timer_start = None
        self._phantom_alerted = False
        self._delta_reported = False
        self._stuck_current_since = None
        self._safe_wait_next_stage = None
        self._analytics_history.clear()
        self._safe_wait_v_samples.clear()

    @property
    def is_active(self) -> bool:
        return self.current_stage != self.STAGE_IDLE

    def _temp_trend(self) -> str:
        """Тренд температуры из temp_history или _analytics_history."""
        h = list(self._analytics_history)
        if len(h) < 6:
            return "→"
        _, _, _, _, t0 = h[-6]
        _, _, _, _, t1 = h[-1]
        delta = t1 - t0
        if delta > 0.5:
            return "↗"
        if delta < -0.5:
            return "↘"
        return "→"

    def _self_discharge_warning(self) -> Optional[str]:
        """Проверка скорости падения V во время SAFE_WAIT при V < 13.5В."""
        if self.current_stage != self.STAGE_SAFE_WAIT or len(self._safe_wait_v_samples) < 2:
            return None
        samples = list(self._safe_wait_v_samples)
        (t0, v0), (t1, v1) = samples[0], samples[-1]
        if t1 <= t0 or v0 >= 13.5 and v1 >= 13.5:
            return None
        dt_hours = (t1 - t0) / 3600.0
        if dt_hours < 0.01:
            return None
        dV_dt = abs(v1 - v0) / dt_hours  # В/час
        avg_v = (v0 + v1) / 2
        if dV_dt > 0.5 and avg_v < 13.5:
            return "⚠️ Высокая скорость падения напряжения: возможно КЗ в банке или сильный саморазряд."
        return None

    def _intelligent_comment(
        self,
        elapsed_min: float,
        ah_delta_30m: float,
        voltage: float,
        current: float,
        ah: float,
    ) -> str:
        """Интеллектуальный комментарий по данным заряда."""
        pct_30m = (ah_delta_30m / self.ah_capacity * 100) if self.ah_capacity > 0 else 0
        ah_charged = ah - self._start_ah if self._start_ah > 0 else ah
        pct_total = (ah_charged / self.ah_capacity * 100) if self.ah_capacity > 0 else 0
        if pct_30m > 5 and voltage >= 14.0:
            return "АКБ активно поглощает заряд."
        if elapsed_min < 30 and current < 0.35 and pct_total < 5:
            return "Внимание: подозрение на потерю ёмкости или сульфатацию."
        return "Нормальный режим заряда."

    def predict_finish(
        self,
        voltage: float,
        current: float,
        ah: float,
        temp: float,
    ) -> Tuple[str, str, Optional[str]]:
        """
        Прогноз времени завершения этапа.
        Возвращает (predicted_time_str, comment, health_warning).
        """
        now = time.time()
        elapsed = now - self.stage_start_time
        elapsed_min = elapsed / 60.0
        h = list(self._analytics_history)
        win_20m = 20 * 60
        recent = [(t, v, i, a, _) for t, v, i, a, _ in h if now - t <= win_20m]
        ah_delta_30m = 0.0
        if len(recent) >= 2:
            ah_delta_30m = recent[-1][3] - recent[0][3]
        comment = self._intelligent_comment(elapsed_min, ah_delta_30m, voltage, current, ah)
        health = self._self_discharge_warning()

        if self.current_stage == self.STAGE_IDLE or self.current_stage == self.STAGE_DONE:
            return "—", comment, health

        if self.current_stage == self.STAGE_SAFE_WAIT:
            threshold = self._safe_wait_target_v - SAFE_WAIT_V_MARGIN
            if voltage <= threshold:
                return "< 1 мин", comment, health
            wait_left = self._safe_wait_start + SAFE_WAIT_MAX_SEC - now
            if wait_left <= 0:
                return "по таймеру", comment, health
            return f"~{int(wait_left / 60)} мин (макс)", comment, health

        i_target = 0.2 if self.battery_type == self.PROFILE_AGM else 0.3
        if self.current_stage in (self.STAGE_MAIN, self.STAGE_MIX) and self.is_cv and len(recent) >= 4:
            ts = [r[0] for r in recent]
            currents = [r[2] for r in recent]
            t0 = ts[0]
            vals = [(t - t0, math.log(max(c, 0.01))) for t, c in zip(ts, currents)]
            if len(vals) >= 4 and currents[-1] > i_target and currents[-1] < currents[0]:
                try:
                    n = len(vals)
                    sum_x = sum(v[0] for v in vals)
                    sum_y = sum(v[1] for v in vals)
                    sum_xx = sum(v[0] ** 2 for v in vals)
                    sum_xy = sum(v[0] * v[1] for v in vals)
                    denom = n * sum_xx - sum_x * sum_x
                    if abs(denom) > 1e-9:
                        slope = (n * sum_xy - sum_x * sum_y) / denom
                        if slope < 0:
                            ln_i_now = math.log(max(currents[-1], 0.01))
                            ln_target = math.log(max(i_target, 0.01))
                            sec_to_target = (ln_target - ln_i_now) / slope if slope != 0 else 0
                            if sec_to_target > 0 and sec_to_target < 24 * 3600:
                                mins = int(sec_to_target / 60)
                                if mins < 60:
                                    return f"~{mins} мин", comment, health
                                return f"~{mins // 60} ч {mins % 60} мин", comment, health
                except (ZeroDivisionError, ValueError):
                    pass

        if self.current_stage == self.STAGE_DESULFATION:
            rem = 2 * 3600 - elapsed
            if rem <= 0:
                return "< 1 мин", comment, health
            return f"~{int(rem / 60)} мин (таймер)", comment, health

        if self.current_stage == self.STAGE_MIX and self.finish_timer_start:
            rem = self.finish_timer_start + MIX_DONE_TIMER - now
            if rem <= 0:
                return "< 1 мин", comment, health
            return f"~{int(rem / 60)} мин (2ч таймер)", comment, health

        if self.current_stage == self.STAGE_MIX and self.battery_type == self.PROFILE_EFB:
            rem = EFB_MIX_MAX_HOURS * 3600 - elapsed
            if rem <= 0:
                return "< 1 мин", comment, health
            return f"~{int(rem / 60)} мин", comment, health

        if self.current_stage == self.STAGE_PREP:
            return "~5–10 мин", comment, health

        return "—", comment, health

    def get_stats(
        self,
        voltage: float,
        current: float,
        ah: float,
        temp: float,
    ) -> Dict[str, Any]:
        """Собрать данные для /stats. elapsed_time = разница между текущим временем и валидным start_time."""
        now = time.time()
        elapsed = now - self.stage_start_time
        if elapsed < 0 or elapsed > ELAPSED_MAX_HOURS * 3600:
            self.stage_start_time = now
            elapsed = 0.0
            logger.warning("get_stats: stage_start_time corrected, elapsed reset")
        hours = int(elapsed // 3600)
        mins = int((elapsed % 3600) / 60)
        elapsed_str = f"{hours} ч {mins} мин" if hours > 0 else f"{mins} мин"
        pred, comment, health = self.predict_finish(voltage, current, ah, temp)
        ah_total = ah - self._start_ah if self._start_ah > 0 else ah
        return {
            "stage": self.current_stage,
            "elapsed_time": elapsed_str,
            "ah_total": ah_total,
            "temp_ext": temp,
            "temp_trend": self._temp_trend(),
            "predicted_time": pred,
            "comment": comment,
            "health_warning": health,
        }

    def get_telemetry_summary(
        self,
        voltage: float,
        current: float,
        ah: float,
        temp: float,
    ) -> Dict[str, Any]:
        """
        Телеметрия для AI: только последние 10–15 мин, с текущей меткой времени.
        """
        now = time.time()
        window_sec = TELEMETRY_HISTORY_MINUTES * 60
        h = [(t, v, i, a, te) for t, v, i, a, te in self._analytics_history if now - t <= window_sec]
        # Для ИИ только последние 10–15 записей + текущее время, чтобы исключить галлюцинации из старых данных
        h = h[-15:] if len(h) > 15 else h
        history = [{"ts": ts, "v": round(v, 2), "i": round(i, 2), "t": round(te, 1)} for ts, v, i, a, te in h]
        ah_charged = ah - self._start_ah if self._start_ah > 0 else ah
        v_drop_rate = None
        if self.current_stage == self.STAGE_SAFE_WAIT and len(self._safe_wait_v_samples) >= 2:
            samples = list(self._safe_wait_v_samples)
            (t0, v0), (t1, v1) = samples[0], samples[-1]
            dt_h = (t1 - t0) / 3600.0
            if dt_h > 0.01:
                v_drop_rate = round((v0 - v1) / dt_h, 2)
        di_dt = dv_dt = None
        if len(h) >= 4:
            ts = [x[0] for x in h]
            vs = [x[1] for x in h]
            cs = [x[2] for x in h]
            dt = ts[-1] - ts[0]
            if dt > 60:
                di_dt = round((cs[-1] - cs[0]) / (dt / 3600.0), 3)
                dv_dt = round((vs[-1] - vs[0]) / (dt / 3600.0), 3)
        return {
            "timestamp": now,
            "timestamp_iso": datetime.fromtimestamp(now).isoformat(),
            "history_minutes": TELEMETRY_HISTORY_MINUTES,
            "history": history,
            "current": {"v": voltage, "i": current, "ah": ah, "temp": temp},
            "stage": self.current_stage,
            "ah_charged": round(ah_charged, 2),
            "v_drop_rate_per_hour": v_drop_rate,
            "di_dt_per_hour": di_dt,
            "dv_dt_per_hour": dv_dt,
            "battery_type": self.battery_type,
        }

    def _ic(self, factor: float) -> float:
        """Ток 0.5C, 0.5*Ah."""
        return max(0.1, factor * self.ah_capacity)

    def _pct_ah(self, pct: float) -> float:
        """Процент от ёмкости в А."""
        return max(0.1, pct * self.ah_capacity / 100.0)

    def _prep_target(self) -> Tuple[float, float]:
        return (12.0, 0.5)

    def _main_target(self) -> Tuple[float, float]:
        if self.battery_type == self.PROFILE_CA:
            return (14.7, self._ic(0.5))
        if self.battery_type == self.PROFILE_EFB:
            return (14.8, self._ic(0.5))
        if self.battery_type == self.PROFILE_AGM:
            v = AGM_STAGES[min(self._agm_stage_idx, len(AGM_STAGES) - 1)]
            return (v, self._ic(0.5))
        return (14.7, self._ic(0.5))

    def _desulf_target(self) -> Tuple[float, float]:
        return (16.3, self._pct_ah(2.0))

    def _mix_target(self) -> Tuple[float, float]:
        if self.battery_type == self.PROFILE_AGM:
            return (16.3, self._pct_ah(2.0))
        return (16.5, self._pct_ah(3.0))

    def _storage_target(self) -> Tuple[float, float]:
        return (13.8, 1.0)

    def _check_temp_safety(
        self,
        temp: float,
        voltage: float,
        current: float,
        ah_charged: float,
        stage_duration_min: float,
    ) -> Optional[str]:
        """
        Проверка температуры (sensor.rd_6018_temperature_external).
        Применяется ко всем режимам (Ca/Ca, EFB, AGM) без исключения.
        Возвращает сообщение об ошибке или None.
        """
        if temp >= TEMP_EMERGENCY:
            return (
                "🔴 <b>АВАРИЙНОЕ ОТКЛЮЧЕНИЕ (ПЕРЕГРЕВ)</b>\n\n"
                f"Температура: <code>{temp:.1f}</code>°C (порог {TEMP_EMERGENCY:.0f}°C)\n"
                f"Текущий этап: <code>{self.current_stage}</code>\n"
                f"Напряжение: <code>{voltage:.2f}</code>В\n"
                f"Ток: <code>{current:.2f}</code>А\n"
                f"Накопленная ёмкость: <code>{ah_charged:.2f}</code> Ач\n"
                f"Время в текущем режиме: <code>{stage_duration_min:.0f}</code> мин."
            )
        if temp >= TEMP_WARNING and not self._temp_34_alerted:
            self._temp_34_alerted = True
            self._pending_log_event = "WARNING_34C"
            self.notify(
                f"⚠️ Внимание: Температура АКБ поднялась до {temp:.1f}°C. Продолжаю наблюдение."
            )
        return None

    def _detect_stuck_current(self, current: float) -> bool:
        """Застревание тока > 0.3A — триггер десульфации."""
        return current > DESULF_CURRENT_STUCK

    def _exit_cc_condition(self, v_now: float) -> bool:
        """Выход CC: V упало на 0.03V от пика."""
        if self.v_max_recorded is None:
            return False
        return v_now <= self.v_max_recorded - DELTA_V_EXIT

    def _exit_cv_condition(self, i_now: float) -> bool:
        """Выход CV: I выросло на 0.03A от минимума."""
        if self.i_min_recorded is None:
            return False
        return i_now >= self.i_min_recorded + DELTA_I_EXIT

    def _get_stage_max_hours(self) -> Optional[float]:
        """Макс. часов этапа для прогресс-репорта, или None если нет лимита."""
        if self.current_stage == self.STAGE_DESULFATION:
            return 2.0
        if self.current_stage == self.STAGE_MIX:
            return 10.0 if self.battery_type == self.PROFILE_EFB else 2.0
        if self.current_stage == self.STAGE_SAFE_WAIT:
            return 2.0
        return None

    def _check_delta_finish(self, v_now: float, i_now: float) -> bool:
        """Проверка условий выхода из Mix (Delta V или Delta I)."""
        if self._exit_cc_condition(v_now):
            return True
        if self._exit_cv_condition(i_now):
            return True
        return False

    async def tick(
        self,
        voltage: float,
        current: float,
        temp_ext: Optional[float],
        is_cv: bool,
        ah: float,
        output_is_on: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Основной цикл. Вызывается из фоновой задачи каждые 30 сек.
        Возвращает dict: set_voltage, set_current, turn_off, notify, emergency_stop.

        output_is_on — последнее известное состояние выхода (on/off); при unavailable
        по нему решаем, слать ли критическое уведомление или тихо перейти в IDLE.

        ВАЖНО: voltage — ВСЕГДА sensor.rd_6018_battery_voltage (напряжение на клеммах АКБ).
        Используется для расчёта дельты (спад 0.03В) и порогов перехода фаз.
        """
        actions: Dict[str, Any] = {}
        now = time.time()
        self.last_update_time = now

        if temp_ext is None or temp_ext in ("unavailable", "unknown", ""):
            self._was_unavailable = True
            actions["emergency_stop"] = True
            actions["log_event"] = "EMERGENCY_UNAVAILABLE"
            if self._last_known_output_on:
                msg = "⚠️ Связь потеряна во время заряда!"
                actions["notify"] = msg
                actions["full_reset"] = True
                self.notify(msg)
            else:
                # Выход был выключен — тихо в IDLE, сессию не чистим (можно восстановить при возврате связи)
                self.stop(clear_session=False)
            return actions

        try:
            temp = float(temp_ext)
        except (ValueError, TypeError):
            msg = (
                "🔴 <b>АВАРИЯ:</b> Некорректные данные датчика температуры. "
                "Заряд остановлен в целях безопасности."
            )
            actions["emergency_stop"] = True
            actions["full_reset"] = True
            actions["notify"] = msg
            actions["log_event"] = "EMERGENCY_TEMP_INVALID"
            self.notify(msg)
            return actions

        # Обновить последнее известное состояние выхода и сбросить флаг unavailable
        if output_is_on is not None and str(output_is_on).lower() not in ("unavailable", "unknown", ""):
            self._last_known_output_on = (output_is_on is True or str(output_is_on).lower() == "on")
        self._was_unavailable = False

        if self.current_stage != self.STAGE_IDLE:
            self._analytics_history.append((now, voltage, current, ah, temp))
            # История V/I: обновление строго раз в минуту (последние 20 мин)
            if now - self._last_v_i_history_time >= TRIGGER_CONFIRM_INTERVAL_SEC:
                self.v_history.append((now, voltage))
                self.i_history.append((now, current))
                self._last_v_i_history_time = now
            elapsed_check = now - self.stage_start_time
            if elapsed_check < 0 or elapsed_check > ELAPSED_MAX_HOURS * 3600:
                self.stage_start_time = now
                logger.warning("tick: stage_start_time corrected (elapsed invalid)")

        if self.emergency_hv_disconnect:
            self.notify(
                "🔴 <b>АВАРИЙНОЕ ОТКЛЮЧЕНИЕ:</b> Потеряна связь с контроллером при высоком напряжении (>15В)!"
            )
            self.emergency_hv_disconnect = False

        elapsed = now - self.stage_start_time
        stage_duration_min = elapsed / 60.0
        err = self._check_temp_safety(temp, voltage, current, ah, stage_duration_min)
        if err:
            actions["emergency_stop"] = True
            actions["full_reset"] = True
            actions["notify"] = err
            actions["log_event"] = "EMERGENCY_37C"
            self.notify(err)
            return actions

        if voltage > MAX_VOLTAGE:
            actions["notify"] = f"<b>⚠️ Напряжение</b> {voltage:.2f}V превышает лимит!"

        if self.current_stage == self.STAGE_IDLE:
            return actions

        if self._pending_log_event:
            actions["log_event"] = self._pending_log_event
            self._pending_log_event = None

        elapsed = now - self.stage_start_time

        if now - self._last_log_time >= 60:
            _log_phase(self.current_stage, voltage, current, temp)
            self._last_log_time = now

        if now - self._last_hourly_report >= 3600:
            self._last_hourly_report = now
            current_hrs = elapsed / 3600.0
            max_hrs = self._get_stage_max_hours()
            max_str = f"{max_hrs:.0f}" if max_hrs is not None else "—"
            report = (
                f"⏳ Прошло {current_hrs:.1f}ч из {max_str} лимита этапа. "
                f"T: {temp:.1f}°C, Ah: {ah:.2f}."
            )
            if "notify" not in actions or not actions["notify"]:
                actions["notify"] = report
            else:
                self.notify(report)

        self.is_cv = is_cv
        
        # v2.5: Отслеживание времени в CV-режиме для правила 40 минут
        if is_cv:
            if self._cv_since is None:
                self._cv_since = now
        else:
            self._cv_since = None

        # --- ПОДГОТОВКА (Soft Start) ---
        if self.current_stage == self.STAGE_PREP:
            uv, ui = self._prep_target()
            if voltage < 12.0:
                actions["set_voltage"] = uv
                actions["set_current"] = ui
            else:
                prev = self.current_stage
                self.current_stage = self.STAGE_MAIN
                self.stage_start_time = now
                self._start_ah = ah
                self.v_max_recorded = None
                self.i_min_recorded = None
                self._blanking_until = now + BLANKING_SEC
                self._delta_trigger_count = 0
                _log_trigger(prev, self.current_stage, "Напряжение достигло 12В, переход к Main Charge")
                uv, ui = self._main_target()
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["notify"] = (
                    "<b>✅ Фаза завершена:</b> Подготовка\n"
                    "<b>🚀 Переход к:</b> Main Charge"
                )
                actions["log_event"] = "PREP->MAIN"

        # --- MAIN CHARGE ---
        elif self.current_stage == self.STAGE_MAIN:
            uv, ui = self._main_target()
            in_blanking = now < self._blanking_until

            if self.battery_type == self.PROFILE_AGM:
                stage_mins = elapsed / 60
                if self._agm_stage_idx < len(AGM_STAGES) - 1 and stage_mins >= AGM_STAGE_MIN_MINUTES:
                    self._agm_stage_idx += 1
                    self.stage_start_time = now
                    uv, ui = self._main_target()
                    _log_trigger(self.STAGE_MAIN, self.STAGE_MAIN, f"AGM ступень {self._agm_stage_idx + 1}/4: {uv:.1f}В, мин на ступени: {AGM_STAGE_MIN_MINUTES}")
                    actions["set_voltage"] = uv
                    actions["set_current"] = ui
                    self._add_phase_limits(actions, uv, ui)
                    actions["notify"] = (
                        f"<b>🚀 AGM ступень {self._agm_stage_idx + 1}/4:</b> "
                        f"{uv:.1f}V"
                    )
                    actions["log_event"] = f"AGM_STAGE_{self._agm_stage_idx + 1}/4"
                else:
                    if not in_blanking and is_cv and current < 0.2:
                        prev = self.current_stage
                        self.current_stage = self.STAGE_MIX
                        self.stage_start_time = now
                        self.v_max_recorded = voltage
                        self.i_min_recorded = current
                        self._blanking_until = now + BLANKING_SEC
                        self._delta_trigger_count = 0
                        _log_trigger(prev, self.current_stage, f"AGM: ток < 0.2А (Текущий: {current:.2f}А)")
                        mxv, mxi = self._mix_target()
                        actions["set_voltage"] = mxv
                        actions["set_current"] = mxi
                        self._add_phase_limits(actions, mxv, mxi)
                        actions["notify"] = (
                            "<b>✅ Фаза завершена:</b> Main Charge\n"
                            "<b>🚀 Переход к:</b> Mix Mode (финальный буст)"
                        )
                        actions["log_event"] = "MAIN->MIX"

            elif not in_blanking and is_cv and self._detect_stuck_current(current):
                if self._stuck_current_since is None:
                    self._stuck_current_since = now
                stuck_mins = int((now - self._stuck_current_since) / 60)
                if self.antisulfate_count < 3 and stuck_mins >= DESULF_STUCK_MIN_MINUTES:
                    self.antisulfate_count += 1
                    self._stuck_current_since = None
                    prev = self.current_stage
                    self.current_stage = self.STAGE_DESULFATION
                    self.stage_start_time = now
                    self.v_max_recorded = None
                    self.i_min_recorded = None
                    self._blanking_until = now + BLANKING_SEC
                    self._delta_trigger_count = 0
                    _log_trigger(prev, self.current_stage, f"Ток застрял > {DESULF_CURRENT_STUCK}А ({current:.2f}А) более {stuck_mins} мин, десульфатация #{self.antisulfate_count}")
                    dv, di = self._desulf_target()
                    actions["set_voltage"] = dv
                    actions["set_current"] = di
                    self._add_phase_limits(actions, dv, di)
                    actions["notify"] = (
                        f"🔧 <b>Десульфатация #{self.antisulfate_count}</b>\n\n"
                        f"Ток застрял на значении <code>{current:.2f}</code>А "
                        f"(выше порога <code>{DESULF_CURRENT_STUCK}</code>А) более <code>{stuck_mins}</code> минут.\n\n"
                        f"<b>Действие:</b> Переходим на лечебный прострел: "
                        f"<code>{dv:.1f}</code>В / <code>{di:.2f}</code>А на 2 часа."
                    )
                    actions["log_event"] = "MAIN->DESULFATION"
                else:
                    self._stuck_current_since = None
                    # v2.5: MAIN->MIX (desulf limit) только после 40 мин CV с током >=0.3А для Ca/EFB
                    cv_minutes = 0.0
                    if self._cv_since is not None:
                        cv_minutes = (now - self._cv_since) / 60.0
                    
                    if (self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB) and 
                        cv_minutes >= MAIN_MIX_STUCK_CV_MIN and current >= 0.3):
                        prev = self.current_stage
                        self.current_stage = self.STAGE_MIX
                        self.stage_start_time = now
                        self.v_max_recorded = voltage
                        self.i_min_recorded = current
                        self._blanking_until = now + BLANKING_SEC
                        self._delta_trigger_count = 0
                        _log_trigger(prev, self.current_stage, f"Лимит десульфаций + 40 мин CV (ток {current:.2f}А >= 0.3А), переход в Mix Mode")
                        mxv, mxi = self._mix_target()
                        actions["set_voltage"] = mxv
                        actions["set_current"] = mxi
                        self._add_phase_limits(actions, mxv, mxi)
                        actions["notify"] = (
                            "<b>✅ Переход к:</b> Mix Mode (перемешивание)\n"
                            f"Лимит десульфаций + 40 мин в CV с током ≥0.3А."
                        )
                        actions["log_event"] = f"MAIN->MIX (desulf limit + {cv_minutes:.1f}min CV)"
                    else:
                        # Ещё рано переходить в MIX — остаёмся в MAIN
                        logger.info("MAIN: desulf limit reached but CV time %.1f min < %d min or current %.2fA < 0.3A", 
                                  cv_minutes, MAIN_MIX_STUCK_CV_MIN, current)

            if not in_blanking and is_cv and current < (0.3 if self.battery_type != self.PROFILE_AGM else 0.2):
                self._stuck_current_since = None
                phantom_note = ""
                if elapsed < PHANTOM_CHARGE_MINUTES * 60 and not self._phantom_alerted:
                    self._phantom_alerted = True
                    phantom_note = "\n\n<b>⚠️ Внимание:</b> Подозрительно быстрый заряд. Проверьте АКБ на сульфатацию или потерю ёмкости (высокое R)."
                    actions["log_event"] = "PHANTOM_CHARGE"
                prev = self.current_stage
                self.current_stage = self.STAGE_MIX
                self.stage_start_time = now
                self.v_max_recorded = voltage
                self.i_min_recorded = current
                self._blanking_until = now + BLANKING_SEC
                self._delta_trigger_count = 0
                _log_trigger(prev, self.current_stage, f"Ток ниже порога (Порог: <0.3А, Текущий: {current:.2f}А), переход в Mix Mode")
                mxv, mxi = self._mix_target()
                actions["set_voltage"] = mxv
                actions["set_current"] = mxi
                self._add_phase_limits(actions, mxv, mxi)
                actions["notify"] = (
                    "<b>✅ Фаза завершена:</b> Main Charge\n"
                    "<b>🚀 Переход к:</b> Mix Mode (перемешивание)"
                    f"{phantom_note}"
                )
                actions["log_event"] = "MAIN->MIX"

        # --- БЕЗОПАСНОЕ ОЖИДАНИЕ (Output OFF, ждём падения V) ---
        elif self.current_stage == self.STAGE_SAFE_WAIT:
            if now - self._last_safe_wait_sample >= 300:
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
            threshold = self._safe_wait_target_v - SAFE_WAIT_V_MARGIN
            wait_elapsed = now - self._safe_wait_start
            if voltage <= threshold:
                prev = self.STAGE_SAFE_WAIT
                next_stage = self._safe_wait_next_stage
                self.current_stage = next_stage
                self.stage_start_time = now
                uv, ui = self._safe_wait_target_v, self._safe_wait_target_i
                self._safe_wait_next_stage = None
                _log_trigger(prev, self.current_stage, f"Напряжение упало до порога (V={voltage:.2f}В <= {threshold:.1f}В)")
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["turn_on"] = True
                self._blanking_until = now + BLANKING_SEC  # после включения выхода — 5 мин тишины по триггерам
                if self.current_stage == self.STAGE_DONE:
                    actions["notify"] = (
                        f"<b>✅ Заряд завершён.</b> Storage {uv:.1f}V/{ui:.1f}А. "
                        f"V_max={self.v_max_recorded:.2f}В." if self.v_max_recorded else f"Storage {uv:.1f}V."
                    )
                    actions["log_event"] = f"DONE ah={ah:.2f}"
                    self._clear_session_file()
                else:
                    self.v_max_recorded = None
                    self.i_min_recorded = None
                    self._blanking_until = now + BLANKING_SEC
                    self._delta_trigger_count = 0
                    actions["notify"] = "<b>🚀 Возврат к Main Charge.</b> Напряжение упало."
                    actions["log_event"] = "SAFE_WAIT->MAIN"
            elif wait_elapsed >= SAFE_WAIT_MAX_SEC:
                prev = self.STAGE_SAFE_WAIT
                next_stage = self._safe_wait_next_stage
                self.current_stage = next_stage
                self.stage_start_time = now
                uv, ui = self._safe_wait_target_v, self._safe_wait_target_i
                self._safe_wait_next_stage = None
                _log_trigger(prev, self.current_stage, "Таймер безопасного ожидания истёк (2 ч), принудительный переход")
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["turn_on"] = True
                self._blanking_until = now + BLANKING_SEC
                actions["notify"] = (
                    "⚠️ Напряжение падает слишком медленно, возможен сильный нагрев или дефект АКБ. "
                    f"Принудительный переход к следующему этапу ({uv:.1f}В)."
                )
                actions["log_event"] = "SAFE_WAIT_FORCED"
                if self.current_stage == self.STAGE_DONE:
                    self._clear_session_file()
                else:
                    self.v_max_recorded = None
                    self.i_min_recorded = None
                    self._blanking_until = now + BLANKING_SEC
                    self._delta_trigger_count = 0
            else:
                pass  # продолжаем ждать

        # --- ДЕСУЛЬФАТАЦИЯ ---
        elif self.current_stage == self.STAGE_DESULFATION:
            if elapsed >= 2 * 3600:
                prev = self.current_stage
                uv, ui = self._main_target()
                threshold = uv - SAFE_WAIT_V_MARGIN  # 14.2В при цели 14.7В
                self.current_stage = self.STAGE_SAFE_WAIT
                self._safe_wait_next_stage = self.STAGE_MAIN
                self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                self._safe_wait_start = now
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
                _log_trigger(prev, self.STAGE_SAFE_WAIT, "Десульфатация 2ч завершена, ожидание падения V")
                actions["turn_off"] = True
                actions["notify"] = (
                    f"<b>⏸ Десульфатация завершена.</b> Ожидание падения до {threshold:.1f}В. "
                    "Выход выключен."
                )
                actions["log_event"] = "DESULFATION->SAFE_WAIT"

        # --- MIX MODE ---
        elif self.current_stage == self.STAGE_MIX:
            if now < self._blanking_until:
                pass
            else:
                if self.v_max_recorded is None or voltage > self.v_max_recorded:
                    self.v_max_recorded = voltage
                if self.i_min_recorded is None or current < self.i_min_recorded:
                    self.i_min_recorded = current

                # Подтверждение: триггер срабатывает только если условие 3 замера подряд с интервалом 1 мин
                if self._check_delta_finish(voltage, current):
                    if now - self._last_delta_confirm_time >= TRIGGER_CONFIRM_INTERVAL_SEC:
                        self._last_delta_confirm_time = now
                        self._delta_trigger_count += 1
                else:
                    self._delta_trigger_count = 0

            if self._delta_trigger_count >= TRIGGER_CONFIRM_COUNT and self._check_delta_finish(voltage, current):
                if not self._delta_reported:
                    self._delta_reported = True
                    self.finish_timer_start = now
                    v_peak = self.v_max_recorded or voltage
                    i_min = self.i_min_recorded or current
                    trigger_msg = ""
                    reason_log = ""
                    if self._exit_cc_condition(voltage):
                        delta_v = v_peak - voltage
                        trigger_msg = (
                            f"🎯 Триггер достигнут: V_max было {v_peak:.2f}В, "
                            f"текущее {voltage:.2f}В. Дельта {delta_v:.3f}В зафиксирована."
                        )
                        reason_log = f"Дельта V: спад от пика (Порог: {DELTA_V_EXIT}В, V_max={v_peak:.2f}В, Текущий={voltage:.2f}В, Подтверждено: {self._delta_trigger_count}/{TRIGGER_CONFIRM_COUNT})"
                    elif self._exit_cv_condition(current):
                        delta_i = current - i_min
                        trigger_msg = (
                            f"🎯 Триггер достигнут: I_min было {i_min:.2f}А, "
                            f"текущее {current:.2f}А. Дельта {delta_i:.3f}А зафиксирована."
                        )
                        reason_log = f"Ток I_min стабилизировался (Порог: +{DELTA_I_EXIT}А от мин, I_min={i_min:.2f}А, Текущий: {current:.2f}А, Подтверждено: {self._delta_trigger_count}/{TRIGGER_CONFIRM_COUNT})"
                    if reason_log:
                        logger.info("[Триггер] %s. Таймер 2ч запущен.", reason_log)
                    actions["notify"] = (
                        f"<b>📉 Отчёт Delta</b>\n{trigger_msg}\n"
                        "Условие выполнено. Таймер 2ч."
                    )
                    # v2.5: расширенное логирование Delta для лог-файла
                    if self._exit_cc_condition(voltage):
                        delta_v = v_peak - voltage
                        actions["log_event"] = (
                            f"DELTA_TRIGGER V_max={v_peak:.2f}В, V_now={voltage:.2f}В, "
                            f"dV={delta_v:.3f}В, confirmed={self._delta_trigger_count}/{TRIGGER_CONFIRM_COUNT}"
                        )
                    elif self._exit_cv_condition(current):
                        delta_i = current - i_min
                        actions["log_event"] = (
                            f"DELTA_TRIGGER I_min={i_min:.2f}А, I_now={current:.2f}А, "
                            f"dI={delta_i:.3f}А, confirmed={self._delta_trigger_count}/{TRIGGER_CONFIRM_COUNT}"
                        )
                    else:
                        actions["log_event"] = f"DELTA_TRIGGER {trigger_msg[:50]}"
                if self.finish_timer_start and (now - self.finish_timer_start) >= MIX_DONE_TIMER:
                    prev = self.current_stage
                    uv, ui = self._storage_target()
                    threshold = uv - SAFE_WAIT_V_MARGIN  # 13.3В
                    self.current_stage = self.STAGE_SAFE_WAIT
                    self._safe_wait_next_stage = self.STAGE_DONE
                    self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                    self._safe_wait_start = now
                    self._safe_wait_v_samples.append((now, voltage))
                    self._last_safe_wait_sample = now
                    _log_trigger(prev, self.STAGE_SAFE_WAIT, "Таймер 2ч после Delta выполнен, ожидание падения V до Storage")
                    actions["turn_off"] = True
                    actions["notify"] = (
                        f"<b>✅ Таймер 2ч выполнен.</b> Ожидание падения до {threshold:.1f}В. "
                        f"V_max={self.v_max_recorded:.2f}В. Выход выключен."
                    )
                    actions["log_event"] = "MIX->SAFE_WAIT"
            elif self.battery_type == self.PROFILE_EFB and elapsed >= EFB_MIX_MAX_HOURS * 3600:
                prev = self.current_stage
                uv, ui = self._storage_target()
                threshold = uv - SAFE_WAIT_V_MARGIN  # 13.3В
                self.current_stage = self.STAGE_SAFE_WAIT
                self._safe_wait_next_stage = self.STAGE_DONE
                self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                self._safe_wait_start = now
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
                _log_trigger(prev, self.STAGE_SAFE_WAIT, "EFB Mix лимит 10ч, ожидание падения V")
                actions["turn_off"] = True
                actions["notify"] = (
                    f"<b>⏱ EFB Mix:</b> лимит 10ч. Ожидание падения до {threshold:.1f}В. "
                    "Выход выключен."
                )
                actions["log_event"] = "MIX->SAFE_WAIT (EFB limit)"

        if "notify" in actions:
            self.notify(actions["notify"])

        if "log_event" in actions:
            actions["log_event"] = f"{actions['log_event']} | {self._session_start_reason}"

        active = self.current_stage in (
            self.STAGE_PREP,
            self.STAGE_MAIN,
            self.STAGE_DESULFATION,
            self.STAGE_MIX,
            self.STAGE_SAFE_WAIT,
        )
        if active and ("notify" in actions or now - self._last_save_time >= 30):
            self._save_session(voltage, current, ah)
            self._last_save_time = now

        return actions
