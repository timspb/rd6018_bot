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
from charging_log import log_session_header

logger = logging.getLogger("rd6018")

SESSION_FILE = "charge_session.json"
SESSION_MAX_AGE = 24 * 60 * 60  # сек — при восстановлении связи всегда пробуем восстановить сессию (до 24 ч), юзеру пишем
SESSION_START_MAX_AGE = 24 * 60 * 60  # сек — если start_time старше 24 ч или 0, принудительно now()

# Пороги детекции
DELTA_V_EXIT = 0.03  # В — выход CC при падении V от пика
DELTA_I_EXIT = 0.03  # А — выход CV при росте I от минимума
TEMP_RISE_LIMIT = 2.0  # °C за 5 мин
TEMP_RISE_WINDOW = 300  # сек (5 мин)
DESULF_CURRENT_STUCK = 0.3  # А — порог «застревания» для Ca/EFB
DESULF_CURRENT_STUCK_AGM = 0.2  # А — порог для AGM
DESULF_STUCK_MIN_MINUTES = 40  # мин — минимум времени застревания перед десульфацией (детектор «полки»)
ANTISULFATE_MAX_CA_EFB = 3  # макс итераций антисульфата для Ca/Ca и EFB
ANTISULFATE_MAX_AGM = 4  # макс итераций для AGM
MIX_DONE_TIMER = 2 * 3600  # сек — таймер после delta до Done
CA_MIX_MAX_HOURS = 8   # Ca/Ca: макс 8 ч на этапе Mix
EFB_MIX_MAX_HOURS = 10
AGM_MIX_MAX_HOURS = 5  # AGM: макс 5 ч на этапе Mix
AGM_STAGES = [14.4, 14.6, 14.8, 15.0]  # В — четырёхступенчатый подъём
AGM_STAGE_MIN_MINUTES = 15  # мин на каждой ступени перед переходом (резерв)
# Ожидание на минимальном токе: Ca/EFB — 3ч на I<0.3А; AGM — на всех ступенях 2ч на I<0.2А без нового минимума
AGM_FIRST_STAGE_HOLD_HOURS = 2  # AGM: на каждой ступени и перед MAIN→MIX
AGM_FIRST_STAGE_HOLD_SEC = AGM_FIRST_STAGE_HOLD_HOURS * 3600
FIRST_STAGE_HOLD_HOURS = 3
FIRST_STAGE_HOLD_SEC = FIRST_STAGE_HOLD_HOURS * 3600
# Режим хранения (V < 14В): прогресс-репорты раз в час, не чаще
STORAGE_REPORT_INTERVAL_SEC = 3600

# Безопасный переход HV -> LV (вместо фиксированной «паузы 30 мин» — ожидание по напряжению)
SAFE_WAIT_V_MARGIN = 0.5  # В — ждать падения до (целевое напряжение следующего этапа − 0.5В)
SAFE_WAIT_MAX_SEC = 2 * 3600  # макс 2 часа ожидания
HIGH_V_FOR_SAFE_WAIT = 15.0  # переходы с V > 15В требуют ожидания
PHANTOM_CHARGE_MINUTES = 10  # мин — ток < порога за это время = подозрительно быстрый заряд
BLANKING_SEC = 5 * 60  # сек — после смены фазы игнорировать триггеры
DELTA_MONITOR_DELAY_SEC = 120  # v2.0: начинать мониторинг dV/dI строго через 120 сек после смены уставок
TRIGGER_CONFIRM_COUNT = 3  # подтверждений подряд с интервалом 1 мин для срабатывания Delta
TRIGGER_CONFIRM_INTERVAL_SEC = 60  # сек — интервал между замерами для подтверждения
MAIN_MIX_STUCK_CV_MIN = 40  # мин в CV с током >=0.3А перед MAIN->MIX (desulf limit) для Ca/EFB
MAIN_STAGE_MAX_HOURS = 72  # защитный лимит для MAIN: 72 часа максимум
CUSTOM_MODE_DEFAULT_MAX_HOURS = 24  # защитный лимит для ручного режима по умолчанию
ELAPSED_MAX_HOURS = 1000  # если elapsed > 1000 ч — ошибка времени, сброс start_time
TELEMETRY_HISTORY_MINUTES = 15  # для AI только последние 15 мин

# Hardware Watchdog
WATCHDOG_TIMEOUT = 5 * 60  # сек — нет данных 5 мин → аварийное отключение
HIGH_V_FAST_TIMEOUT = 60  # сек — при U>15В: нет данных 60 сек → немедленное отключение
HIGH_V_THRESHOLD = 15.0  # В — порог для ускоренного watchdog

# Активная безопасность: OVP/OCP (v2.0: при каждой смене этапа)
OVP_OFFSET = 0.1  # В — OVP = U_target + 0.1V
OCP_OFFSET = 0.1  # А — OCP = I_limit + 0.1A
MAX_STAGE_CURRENT = 12.0  # А — жесткий лимит тока на всех этапах
# Температура: ТОЛЬКО внешний датчик (АКБ). 35/40/45 — три уровня.
TEMP_WARNING = 35.0  # °C — предупреждение в Telegram (один раз за сессию)
TEMP_PAUSE = 40.0    # °C — пауза заряда (Output OFF), возврат при 35°C
TEMP_CRITICAL = 45.0  # °C — аварийная остановка ТОЛЬКО по внешнему датчику АКБ


def _log_phase(phase: str, v: float, i: float, t: float) -> None:
    """Лог в консоль: Время | Фаза | V | I | T."""
    from time_utils import format_time_user_tz
    ts = format_time_user_tz()
    logger.info("%s | %-12s | %5.2fВ | %5.2fА | %5.1f°C", ts, phase, v, i, t)


def _log_trigger(from_stage: str, to_stage: str, trigger_name: str, condition: str = "") -> None:
    """v2.6 Детализированное логирование смены этапа с условием."""
    from time_utils import format_time_user_tz
    ts = format_time_user_tz()
    if condition:
        msg = f"[{ts}] {from_stage} -> {to_stage} | Причина: {trigger_name} | Значение: {condition}"
    else:
        msg = f"[{ts}] {from_stage} -> {to_stage} | Причина: {trigger_name}"
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
    STAGE_COOLING = "🌡 Остывание"
    STAGE_DONE = "Done"
    STAGE_IDLE = "Idle"

    PROFILE_CA = "Ca/Ca"
    PROFILE_EFB = "EFB"
    PROFILE_AGM = "AGM"
    PROFILE_CUSTOM = "Custom"

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
        # Ограничиваем память: 24 часа данных при интервале 30 сек = 2880 точек
        self.temp_history: deque = deque(maxlen=100)  # ~50 мин истории температуры
        self._last_log_time: float = 0.0
        self._agm_stage_idx: int = 0
        self._delta_reported: bool = False
        self.is_cv: bool = False
        self._stuck_current_since: Optional[float] = None  # когда ток впервые вышел на полку выше порога десульфации
        self._stuck_current_value: Optional[float] = None  # минимум тока на текущей полке; новый минимум сбрасывает таймер
        self.last_update_time: float = 0.0  # время последнего вызова tick() — для watchdog
        self.emergency_hv_disconnect: bool = False  # флаг после аварийного отключения при U>15В
        self._phase_current_limit: float = 0.0  # базовый лимит тока текущей фазы
        self._temp_warning_alerted: bool = False  # предупреждение 35°C отправлено один раз за сессию
        self._cooling_from_stage: Optional[str] = None  # из какого этапа перешли в охлаждение
        self._cooling_target_v: float = 0.0  # целевые параметры для возврата
        self._cooling_target_i: float = 0.0
        self._pending_log_event: Optional[str] = None  # для логирования событий
        self._start_ah: float = 0.0  # накопленная ёмкость на старте сессии
        self._stage_start_ah: float = 0.0  # ёмкость на входе в текущий этап (для лога завершения)
        self._last_checkpoint_time: float = 0.0  # для контрольных точек каждые 10 мин
        self._last_save_time: float = 0.0
        self._safe_wait_next_stage: Optional[str] = None  # куда перейти после ожидания
        self._safe_wait_target_v: float = 0.0
        self._safe_wait_target_i: float = 0.0
        self._safe_wait_start: float = 0.0
        self._last_hourly_report: float = 0.0  # для прогресс-репортов раз в час
        # Оптимизация памяти: ограничиваем историю 24 часами (2880 точек при 30с интервале)
        self._analytics_history: deque = deque(maxlen=1000)  # ~8.3 часа истории при 30с
        self._safe_wait_v_samples: deque = deque(maxlen=288)  # 24 часа при замере каждые 5 мин
        self._last_safe_wait_sample: float = 0.0
        self._blanking_until: float = 0.0  # до этого времени игнорировать триггеры после смены фазы
        self._delta_monitor_after: float = 0.0  # v2.0: мониторинг dV/dI только после этого времени (120 сек после смены уставок)
        self._delta_trigger_count: int = 0  # подряд выполнений условия Delta для подтверждения
        self._session_start_reason: str = "User Command"  # User Command | Auto-restore
        self._last_known_output_on: bool = False  # последнее известное состояние выхода (для EMERGENCY_UNAVAILABLE)
        self._was_unavailable: bool = False  # предыдущий тик был unavailable → при восстановлении попробовать restore
        self._link_lost_at: float = 0.0  # время потери связи (для вычитания паузы из таймеров при восстановлении)
        self._restored_target_v: float = 0.0  # уставки из сессии при restore (чтобы не перезаписать дефолтами профиля)
        self._restored_target_i: float = 0.0
        self._device_set_voltage: Optional[float] = None  # фактические уставки прибора (для сохранения в сессию)
        self._device_set_current: Optional[float] = None
        # История замеров V/I за последние 24 часа, обновление раз в минуту
        self.v_history: deque = deque(maxlen=1440)  # 24 часа при замере каждую минуту
        self.i_history: deque = deque(maxlen=1440)  # 24 часа при замере каждую минуту
        self._last_v_i_history_time: float = 0.0
        self._last_delta_confirm_time: float = 0.0  # для подтверждения триггера раз в 1 мин
        self._cv_since: Optional[float] = None  # v2.5: время начала CV-режима для отслеживания 40 мин
        self.total_start_time: float = 0.0  # v2.6: общий старт сессии заряда (не сбрасывается при смене этапов)
        self._first_stage_hold_since: Optional[float] = None  # с какого момента ток на минимуме (ждём FIRST_STAGE_HOLD_SEC без нового минимума)
        self._first_stage_hold_current: Optional[float] = None  # значение тока в момент старта 3ч — при новом минимуме таймер сбрасывается
        # Переменные для ручного режима
        self._custom_main_voltage: float = 14.7
        self._custom_main_current: float = 5.0
        self._custom_delta_threshold: float = 0.03
        self._custom_time_limit_hours: float = 24.0

    def _add_phase_limits(self, actions: Dict[str, Any], target_v: float, target_i: float) -> None:
        """v2.0: Добавить OVP/OCP в actions при смене фазы. OVP = U_target + 0.2V, OCP = I_limit + 0.2A."""
        actions["set_ovp"] = target_v + OVP_OFFSET
        actions["set_ocp"] = target_i + OCP_OFFSET
        self._phase_current_limit = target_i

    def _reset_delta_and_blanking(self, now: float) -> None:
        """v2.0: Полный сброс при смене этапа/уставок — исключает ложный DELTA_TRIGGER после Main->Mix."""
        self.v_max_recorded = None
        self.i_min_recorded = None
        self._delta_trigger_count = 0
        self._first_stage_hold_since = None
        self._first_stage_hold_current = None
        self._stuck_current_since = None
        self._stuck_current_value = None
        self._blanking_until = now + DELTA_MONITOR_DELAY_SEC
        self._delta_monitor_after = now + DELTA_MONITOR_DELAY_SEC

    def start(self, battery_type: str, ah_capacity: int) -> None:
        """Запуск заряда по профилю."""
        # v2.6 Сброс данных сессии при старте нового заряда
        self.reset_session_data()
        
        self.battery_type = battery_type
        self.ah_capacity = max(1, ah_capacity)
        self.current_stage = self.STAGE_PREP
        self.stage_start_time = time.time()
        self._stage_start_ah = 0.0  # будет установлен при первом tick()
        self.total_start_time = self.stage_start_time  # v2.6: фиксируем общий старт сессии
        self.antisulfate_count = 0
        self.v_max_recorded = None
        self.i_min_recorded = None
        self.finish_timer_start = None
        self._phantom_alerted = False
        self.temp_history.clear()
        self._agm_stage_idx = 0
        self._delta_reported = False
        self._stuck_current_since = None
        self._stuck_current_value = None
        self.emergency_hv_disconnect = False
        self._temp_warning_alerted = False
        self._pending_log_event = None
        self._safe_wait_next_stage = None
        self._safe_wait_target_v = 0.0
        self._safe_wait_target_i = 0.0
        self._safe_wait_start = 0.0
        self._blanking_until = 0.0
        self._delta_trigger_count = 0
        self._last_delta_confirm_time = 0.0
        self._cv_since = None
        self._first_stage_hold_since = None
        self._first_stage_hold_current = None
        self._session_start_reason = "User Command"
        self._clear_restored_targets()
        self._clear_session_file()
        target_v, target_i = self._get_target_v_i()
        log_session_header(
            "start",
            self.current_stage,
            0.0,
            0.0,
            0.0,
            0.0,
            self.battery_type,
            self.ah_capacity,
            self._session_rules_summary(),
            meta={
                "session_reason": self._session_start_reason,
                "target_v": f"{target_v:.2f}",
                "target_i": f"{target_i:.2f}",
            },
        )
        logger.info("ChargeController started: %s %dAh (%s)", battery_type, self.ah_capacity, self._session_start_reason)

    def start_custom(self, main_voltage: float, main_current: float, delta_threshold: float, 
                    time_limit_hours: float, ah_capacity: int) -> None:
        """Запуск заряда в ручном режиме с пользовательскими параметрами."""
        # Сброс данных сессии при старте нового заряда
        self.reset_session_data()
        
        self.battery_type = self.PROFILE_CUSTOM
        self.ah_capacity = max(1, ah_capacity)
        self.current_stage = self.STAGE_MAIN  # Ручной режим сразу начинает с MAIN
        self.stage_start_time = time.time()
        self._stage_start_ah = 0.0  # будет установлен при первом tick()
        self.total_start_time = self.stage_start_time
        
        # Сохраняем пользовательские параметры
        self._custom_main_voltage = main_voltage
        self._custom_main_current = min(MAX_STAGE_CURRENT, max(0.1, main_current))
        self._custom_delta_threshold = delta_threshold
        self._custom_time_limit_hours = max(1.0, time_limit_hours)  # Минимум 1 час
        
        # Сброс всех счетчиков и флагов
        self.antisulfate_count = 0
        self.v_max_recorded = None
        self.i_min_recorded = None
        self.finish_timer_start = None
        self._phantom_alerted = False
        self.temp_history.clear()
        self._agm_stage_idx = 0
        self._delta_reported = False
        self._stuck_current_since = None
        self._stuck_current_value = None
        self.emergency_hv_disconnect = False
        self._temp_warning_alerted = False
        self._cooling_from_stage = None
        self._cooling_target_v = 0.0
        self._cooling_target_i = 0.0
        self._pending_log_event = None
        self._safe_wait_next_stage = None
        self._safe_wait_target_v = 0.0
        self._safe_wait_target_i = 0.0
        self._safe_wait_start = 0.0
        self._blanking_until = time.time() + DELTA_MONITOR_DELAY_SEC
        self._delta_monitor_after = time.time() + DELTA_MONITOR_DELAY_SEC
        self._first_stage_hold_since = None
        self._first_stage_hold_current = None
        self._delta_trigger_count = 0
        self._last_delta_confirm_time = 0.0
        self._cv_since = None
        self._session_start_reason = "Custom Mode"
        self._clear_restored_targets()
        self._clear_session_file()
        target_v, target_i = self._get_target_v_i()
        log_session_header(
            "start",
            self.current_stage,
            0.0,
            0.0,
            0.0,
            0.0,
            self.battery_type,
            self.ah_capacity,
            self._session_rules_summary(),
            meta={
                "session_reason": self._session_start_reason,
                "target_v": f"{target_v:.2f}",
                "target_i": f"{target_i:.2f}",
                "delta_threshold": f"{self._custom_delta_threshold:.3f}",
                "time_limit_h": f"{self._custom_time_limit_hours:.1f}",
            },
        )
        
        logger.info("ChargeController started CUSTOM: %.1fV/%.1fA delta=%.3fV limit=%.0fh capacity=%dAh", 
                   main_voltage, main_current, delta_threshold, time_limit_hours, ah_capacity)

    def stop(self, clear_session: bool = True) -> None:
        """Остановка заряда. Если clear_session=False, файл сессии не удаляется (для восстановления после связи)."""
        prev = self.current_stage
        if prev == self.STAGE_IDLE:
            return  # уже остановлен — не дублировать лог при повторных вызовах (напр. при unavailable)
        self.current_stage = self.STAGE_IDLE
        self._clear_restored_targets()
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
            if self.battery_type == self.PROFILE_CA:
                return self.stage_start_time + CA_MIX_MAX_HOURS * 3600
            if self.battery_type == self.PROFILE_AGM:
                return self.stage_start_time + AGM_MIX_MAX_HOURS * 3600
        return None

    def _clear_restored_targets(self) -> None:
        """Сбросить уставки, восстановленные из сессии (после перехода на другой этап)."""
        self._restored_target_v = 0.0
        self._restored_target_i = 0.0

    def _get_target_v_i(self) -> Tuple[float, float]:
        """Текущие целевые V и I для фазы. При restore возвращаем сохранённые уставки из сессии."""
        if self._restored_target_v > 0 and self._restored_target_i > 0:
            return (self._restored_target_v, self._restored_target_i)
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
        if self.current_stage == self.STAGE_COOLING:
            return (0.0, 0.0)  # выход выключен во время охлаждения
        if self.current_stage == self.STAGE_DONE:
            return self._storage_target()
        return (0.0, 0.0)

    def _save_session(self, voltage: float, current: float, ah: float) -> None:
        """Сохранить текущее состояние в charge_session.json. Уставки — с прибора, если известны."""
        if self.current_stage in (self.STAGE_IDLE, self.STAGE_DONE):
            return
        target_finish = self._get_target_finish_time()
        if self.current_stage == self.STAGE_SAFE_WAIT:
            uv, ui = self._safe_wait_target_v, self._safe_wait_target_i
        elif self.current_stage == self.STAGE_COOLING:
            uv, ui = self._cooling_target_v, self._cooling_target_i
        else:
            uv, ui = self._get_target_v_i()
        # Сохраняем фактические уставки прибора (до потери связи/перезапуска)
        if self._device_set_voltage is not None and self._device_set_voltage > 0 and self._device_set_current is not None and self._device_set_current > 0:
            uv, ui = self._device_set_voltage, self._device_set_current
        else:
            # С прибора уставки не приходили — не перезаписывать дефолтами профиля; сохранить из файла, если есть
            if os.path.exists(SESSION_FILE):
                try:
                    with open(SESSION_FILE, "r", encoding="utf-8") as f:
                        old = json.load(f)
                    tv, ti = float(old.get("target_voltage", 0) or 0), float(old.get("target_current", 0) or 0)
                    if tv > 0 and ti > 0:
                        uv, ui = tv, ti
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
        data = {
            "profile": self.battery_type,
            "stage": self.current_stage,
            "stage_start_time": self.stage_start_time,
            "target_finish_time": target_finish,
            "finish_timer_start": self.finish_timer_start,
            "ah_limit": self.ah_capacity,
            "start_ah": self._start_ah,
            "stage_start_ah": self._stage_start_ah,
            "current_retries": self.antisulfate_count,
            "target_voltage": uv,
            "target_current": ui,
            "agm_stage_idx": self._agm_stage_idx,
            "safe_wait_next_stage": self._safe_wait_next_stage,
            "safe_wait_target_v": self._safe_wait_target_v,
            "safe_wait_target_i": self._safe_wait_target_i,
            "safe_wait_start": self._safe_wait_start,
            "total_start_time": self.total_start_time,  # v2.6: сохраняем общий старт
            "first_stage_hold_since": self._first_stage_hold_since,
            "first_stage_hold_current": self._first_stage_hold_current,
            "stuck_current_since": self._stuck_current_since,
            "stuck_current_value": self._stuck_current_value,
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
        self._agm_stage_idx = max(0, min(self._agm_stage_idx, len(AGM_STAGES) - 1))
        self._start_ah = float(data.get("start_ah", 0))
        self._stage_start_ah = float(data.get("stage_start_ah", ah))  # при отсутствии — текущий ah
        self._safe_wait_next_stage = data.get("safe_wait_next_stage")
        self._safe_wait_target_v = float(data.get("safe_wait_target_v", 0))
        self._safe_wait_target_i = float(data.get("safe_wait_target_i", 0))
        now = time.time()
        raw_safe_wait_start = data.get("safe_wait_start")
        try:
            self._safe_wait_start = float(raw_safe_wait_start) if raw_safe_wait_start not in (None, 0) else now
        except (TypeError, ValueError):
            self._safe_wait_start = now
        if self.current_stage == self.STAGE_SAFE_WAIT:
            allowed_safe_wait_next = {self.STAGE_MAIN, self.STAGE_DONE}
            if self._safe_wait_next_stage not in allowed_safe_wait_next:
                logger.warning(
                    "Restore: invalid safe_wait_next_stage=%r, fallback to %s",
                    self._safe_wait_next_stage,
                    self.STAGE_MAIN,
                )
                self._safe_wait_next_stage = self.STAGE_MAIN
        else:
            self._safe_wait_next_stage = None
        raw_hold_since = data.get("first_stage_hold_since")
        try:
            self._first_stage_hold_since = float(raw_hold_since) if raw_hold_since not in (None, 0) else None
        except (TypeError, ValueError):
            self._first_stage_hold_since = None
        raw_hold_current = data.get("first_stage_hold_current")
        try:
            self._first_stage_hold_current = float(raw_hold_current) if raw_hold_current is not None else None
        except (TypeError, ValueError):
            self._first_stage_hold_current = None
        raw_stuck_since = data.get("stuck_current_since")
        try:
            self._stuck_current_since = float(raw_stuck_since) if raw_stuck_since not in (None, 0) else None
        except (TypeError, ValueError):
            self._stuck_current_since = None
        raw_stuck_value = data.get("stuck_current_value")
        try:
            self._stuck_current_value = float(raw_stuck_value) if raw_stuck_value is not None else None
        except (TypeError, ValueError):
            self._stuck_current_value = None

        # v2.6: восстанавливаем общий старт сессии
        raw_total_start = data.get("total_start_time")
        try:
            self.total_start_time = float(raw_total_start) if raw_total_start not in (None, 0) else now
        except (TypeError, ValueError):
            self.total_start_time = now
        # Валидация total_start_time
        if not self.total_start_time or self.total_start_time <= 0 or (now - self.total_start_time) > SESSION_START_MAX_AGE:
            self.total_start_time = now
            logger.info("Restore: total_start_time invalid or >24h, set to now()")

        target_finish = data.get("target_finish_time")
        target_v = float(data.get("target_voltage", 14.7))
        target_i = float(data.get("target_current", 1.0))
        target_i = min(MAX_STAGE_CURRENT, max(0.1, target_i))
        self._restored_target_v = target_v
        self._restored_target_i = target_i
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
                    self._clear_restored_targets()
                    self.stage_start_time = now
                elif self.current_stage == self.STAGE_MIX:
                    self.current_stage = self.STAGE_DONE
                    self._clear_restored_targets()
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

        self._reset_delta_and_blanking(now)
        if self.current_stage == self.STAGE_MAIN:
            raw_stuck_since = data.get("stuck_current_since")
            try:
                self._stuck_current_since = float(raw_stuck_since) if raw_stuck_since not in (None, 0) else None
            except (TypeError, ValueError):
                self._stuck_current_since = None
            raw_stuck_value = data.get("stuck_current_value")
            try:
                self._stuck_current_value = float(raw_stuck_value) if raw_stuck_value is not None else None
            except (TypeError, ValueError):
                self._stuck_current_value = None
        if self.current_stage != self.STAGE_MIX:
            self.finish_timer_start = None

        # Синхронизация таймеров с прибором: оцениваем время по накопленным А·ч и току
        i_avg = max(float(current), 0.1)
        delta_ah_total = ah - self._start_ah
        delta_ah_stage = ah - self._stage_start_ah
        if delta_ah_total > 0.01 and i_avg > 0.05:
            est_total_h = delta_ah_total / i_avg
            est_total_h = min(est_total_h, SESSION_START_MAX_AGE / 3600)
            self.total_start_time = now - est_total_h * 3600
            logger.info("Restore: total_start_time synced from Ah: %.1f h elapsed", est_total_h)
        if delta_ah_stage > 0.01 and i_avg > 0.05:
            est_stage_h = delta_ah_stage / i_avg
            est_stage_h = min(est_stage_h, SESSION_START_MAX_AGE / 3600)
            self.stage_start_time = now - est_stage_h * 3600
            logger.info("Restore: stage_start_time synced from Ah: %.1f h on stage", est_stage_h)

        elapsed_sec = now - self.stage_start_time
        if elapsed_sec < 0 or elapsed_sec > ELAPSED_MAX_HOURS * 3600:
            self.stage_start_time = now
            logger.warning("Restore: stage_start_time corrected (elapsed invalid)")
        restored_stage_limit = self._get_stage_max_hours()
        restored_target_v, restored_target_i = self._get_target_v_i()
        log_session_header(
            "restore",
            self.current_stage,
            voltage,
            current,
            0.0,
            ah,
            self.battery_type,
            self.ah_capacity,
            self._session_rules_summary(),
            meta={
                "session_reason": self._session_start_reason,
                "stage_limit_h": f"{restored_stage_limit:.1f}" if restored_stage_limit is not None else "—",
                "target_v": f"{restored_target_v:.2f}",
                "target_i": f"{restored_target_i:.2f}",
                "remaining_min": remaining_min,
            },
        )
        return True, msg

    def reset_session_data(self) -> None:
        """v2.6 Сброс данных сессии: счетчик Ач, история графиков, временный лог событий.
        Вызывается ТОЛЬКО при старте нового заряда через меню РЕЖИМЫ."""
        logger.info("reset_session_data: clearing session history and counters")
        # Очистка истории для графиков
        self._analytics_history.clear()
        self.v_history.clear()
        self.i_history.clear()
        self._safe_wait_v_samples.clear()
        
        # Сброс счетчиков и временных данных
        self._start_ah = 0.0
        self._stage_start_ah = 0.0
        self._last_checkpoint_time = 0.0
        self._last_hourly_report = 0.0
        self._last_v_i_history_time = 0.0
        self._last_safe_wait_sample = 0.0
        self._stuck_current_since = None
        self._stuck_current_value = None
        self._first_stage_hold_since = None
        self._first_stage_hold_current = None
        
        # Очистка временного лога событий (если будет реализован)
        # self._event_log.clear()  # TODO: добавить когда будет event log

    def full_reset(self) -> None:
        """Полный сброс состояния (при аварийном отключении по температуре)."""
        self.stop()
        self.temp_history.clear()
        self._temp_warning_alerted = False
        self.finish_timer_start = None
        self._phantom_alerted = False
        self._delta_reported = False
        self._stuck_current_since = None
        self._stuck_current_value = None
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

    def get_timers(self) -> Dict[str, Any]:
        """v2.6 Получить данные таймеров для отображения и AI."""
        now = time.time()
        
        # Общее время заряда
        total_elapsed = now - self.total_start_time if self.total_start_time > 0 else 0
        total_hours = int(total_elapsed // 3600)
        total_mins = int((total_elapsed % 3600) // 60)
        total_str = f"{total_hours:02d}:{total_mins:02d}"
        
        # Время в текущем этапе
        stage_elapsed = now - self.stage_start_time if self.stage_start_time > 0 else 0
        
        # Защита от бага: stage_time не может быть больше total_time
        if stage_elapsed > total_elapsed:
            stage_elapsed = total_elapsed
            
        stage_hours = int(stage_elapsed // 3600)
        stage_mins = int((stage_elapsed % 3600) // 60)
        stage_str = f"{stage_hours:02d}:{stage_mins:02d}"
        
        # Оставшееся время до лимита текущего этапа
        remaining_str = "—"
        stage_limit_sec = None
        
        if self.current_stage == self.STAGE_MAIN:
            stage_limit_sec = MAIN_STAGE_MAX_HOURS * 3600  # 72 часа защитный лимит
        elif self.current_stage == self.STAGE_DESULFATION:
            stage_limit_sec = 2 * 3600  # 2 часа
        elif self.current_stage == self.STAGE_MIX:
            if self.finish_timer_start:
                stage_limit_sec = MIX_DONE_TIMER
                stage_elapsed = now - self.finish_timer_start
            elif self.battery_type == self.PROFILE_EFB:
                stage_limit_sec = EFB_MIX_MAX_HOURS * 3600
            elif self.battery_type == self.PROFILE_CA:
                stage_limit_sec = CA_MIX_MAX_HOURS * 3600
            elif self.battery_type == self.PROFILE_AGM:
                stage_limit_sec = AGM_MIX_MAX_HOURS * 3600
            else:
                stage_limit_sec = MIX_DONE_TIMER
        elif self.current_stage == self.STAGE_SAFE_WAIT:
            stage_limit_sec = SAFE_WAIT_MAX_SEC  # 2 часа
            stage_elapsed = now - self._safe_wait_start if self._safe_wait_start > 0 else 0
        
        if stage_limit_sec:
            remaining_sec = stage_limit_sec - stage_elapsed
            if remaining_sec > 0:
                rem_hours = int(remaining_sec // 3600)
                rem_mins = int((remaining_sec % 3600) // 60)
                remaining_str = f"{rem_hours:02d}:{rem_mins:02d}"
            else:
                remaining_str = "00:00"
        
        return {
            "total_time": total_str,
            "stage_time": stage_str,
            "remaining_time": remaining_str,
            "total_elapsed_sec": total_elapsed,
            "stage_elapsed_sec": stage_elapsed,
            "stage_limit_sec": stage_limit_sec,
        }

    def _format_seconds(self, seconds: Optional[float]) -> str:
        if seconds is None:
            return "—"
        seconds = max(0.0, float(seconds))
        if seconds < 60:
            return f"{int(seconds)}с"
        minutes = seconds / 60
        if minutes < 60:
            return f"{int(minutes)}м"
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        if mins:
            return f"{hours}ч {mins}м"
        return f"{hours}ч"

    def _session_rules_summary(self) -> str:
        if self.battery_type == self.PROFILE_CA:
            return "Main 14.7V; 0.3A/3h -> Mix 16.5V; Mix 8h; SafeWait 2h."
        if self.battery_type == self.PROFILE_EFB:
            return "Main 14.8V; 0.3A/3h -> Mix 16.5V; Mix 10h; SafeWait 2h."
        if self.battery_type == self.PROFILE_AGM:
            return "Main 14.4/14.6/14.8/15.0V; 0.2A/2h -> Mix 16.3V; Mix 5h; SafeWait 2h."
        if self.battery_type == self.PROFILE_CUSTOM:
            return f"Custom {self._custom_main_voltage:.1f}V/{self._custom_main_current:.1f}A; delta={self._custom_delta_threshold:.3f}; limit={self._custom_time_limit_hours:.1f}h."
        return "Rules unavailable."

    def _get_ai_hold_snapshot(self, now: float) -> Optional[Dict[str, Any]]:
        """Короткий снимок удержания тока/таймера для AI."""
        if self.current_stage == self.STAGE_MAIN:
            if self.battery_type == self.PROFILE_AGM:
                threshold = DESULF_CURRENT_STUCK_AGM
                required_sec = AGM_FIRST_STAGE_HOLD_SEC
                hold_kind = "AGM low-current hold"
            elif self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB):
                threshold = DESULF_CURRENT_STUCK
                required_sec = FIRST_STAGE_HOLD_SEC
                hold_kind = "low-current hold"
            else:
                return None

            if self._first_stage_hold_since is None or self._first_stage_hold_current is None:
                return {
                    "active": False,
                    "kind": hold_kind,
                    "threshold_a": threshold,
                    "required_sec": required_sec,
                }

            elapsed = max(0.0, now - self._first_stage_hold_since)
            remaining = max(0.0, required_sec - elapsed)
            return {
                "active": True,
                "kind": hold_kind,
                "threshold_a": threshold,
                "required_sec": required_sec,
                "elapsed_sec": elapsed,
                "remaining_sec": remaining,
                "elapsed_text": self._format_seconds(elapsed),
                "remaining_text": self._format_seconds(remaining),
                "current_a": self._first_stage_hold_current,
                "rule_met": elapsed >= required_sec,
                "needs_new_minimum": True,
            }

        if self.current_stage == self.STAGE_DESULFATION:
            elapsed = max(0.0, now - self.stage_start_time)
            remaining = max(0.0, 2 * 3600 - elapsed)
            return {
                "active": True,
                "kind": "desulf timer",
                "required_sec": 2 * 3600,
                "elapsed_sec": elapsed,
                "remaining_sec": remaining,
                "elapsed_text": self._format_seconds(elapsed),
                "remaining_text": self._format_seconds(remaining),
                "rule_met": elapsed >= 2 * 3600,
            }

        if self.current_stage == self.STAGE_MIX and self.finish_timer_start is not None:
            elapsed = max(0.0, now - self.finish_timer_start)
            remaining = max(0.0, MIX_DONE_TIMER - elapsed)
            return {
                "active": True,
                "kind": "mix delta timer",
                "required_sec": MIX_DONE_TIMER,
                "elapsed_sec": elapsed,
                "remaining_sec": remaining,
                "elapsed_text": self._format_seconds(elapsed),
                "remaining_text": self._format_seconds(remaining),
                "rule_met": elapsed >= MIX_DONE_TIMER,
            }

        if self.current_stage == self.STAGE_SAFE_WAIT:
            elapsed = max(0.0, now - self._safe_wait_start)
            remaining = max(0.0, SAFE_WAIT_MAX_SEC - elapsed)
            threshold = self._safe_wait_target_v - SAFE_WAIT_V_MARGIN
            return {
                "active": True,
                "kind": "safe wait",
                "required_sec": SAFE_WAIT_MAX_SEC,
                "elapsed_sec": elapsed,
                "remaining_sec": remaining,
                "elapsed_text": self._format_seconds(elapsed),
                "remaining_text": self._format_seconds(remaining),
                "threshold_v": threshold,
                "target_v": self._safe_wait_target_v,
                "rule_met": elapsed >= SAFE_WAIT_MAX_SEC,
            }

        return None

    def get_ai_stage_snapshot(self) -> Dict[str, Any]:
        """Собрать компактный снимок стратегии и состояния для LLM."""
        now = time.time()
        target_v, target_i = self._get_target_v_i()
        timers = self.get_timers()
        hold = self._get_ai_hold_snapshot(now)

        if self.current_stage == self.STAGE_PREP:
            summary = "Soft Start 12.0V/0.5A, затем Main."
            next_stage = self.STAGE_MAIN
            transition = "Переход в Main по завершении подготовки."
        elif self.current_stage == self.STAGE_MAIN:
            if self.battery_type == self.PROFILE_AGM:
                summary = "Main по ступеням 14.4 -> 14.6 -> 14.8 -> 15.0V."
                next_stage = self.STAGE_MIX
                transition = "Следующая ступень и переход в Mix: ток ниже 0.2A 2ч без нового минимума."
            elif self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB):
                summary = f"Main {target_v:.1f}V для профиля; hold по низкому току и возможная Desulfation."
                next_stage = self.STAGE_MIX
                transition = "Переход в Mix: ток ниже 0.3A 3ч без нового минимума; при CV-полке >=40 мин возможна Desulfation."
            else:
                summary = "Main по пользовательским уставкам и delta-правилу."
                next_stage = self.STAGE_MIX
                transition = "Переход по delta-триггеру: 3 подтверждения с интервалом 1 мин после включения мониторинга."
        elif self.current_stage == self.STAGE_DESULFATION:
            summary = "Сервисная десульфатация 16.3V / 2%Ah / 2ч."
            next_stage = self.STAGE_SAFE_WAIT
            transition = "После 2ч -> SAFE_WAIT, затем возврат в Main."
        elif self.current_stage == self.STAGE_MIX:
            if self.finish_timer_start is not None:
                summary = "Mix после delta-триггера: таймер 2ч до Done."
                next_stage = self.STAGE_SAFE_WAIT
                transition = "Завершение по таймеру 2ч после delta, затем SAFE_WAIT."
            elif self.battery_type == self.PROFILE_EFB:
                summary = "Mix 16.5V / 0.03C до лимита 10ч."
                next_stage = self.STAGE_SAFE_WAIT
                transition = "Переход в SAFE_WAIT после лимита 10ч."
            elif self.battery_type == self.PROFILE_CA:
                summary = "Mix 16.5V / 0.03C до лимита 8ч."
                next_stage = self.STAGE_SAFE_WAIT
                transition = "Переход в SAFE_WAIT после лимита 8ч."
            elif self.battery_type == self.PROFILE_AGM:
                summary = "Mix 16.3V / 0.03C до лимита 5ч."
                next_stage = self.STAGE_SAFE_WAIT
                transition = "Переход в SAFE_WAIT после лимита 5ч."
            else:
                summary = "Mix по пользовательским правилам."
                next_stage = self.STAGE_SAFE_WAIT
                transition = "Переход по пользовательскому delta или таймеру."
        elif self.current_stage == self.STAGE_SAFE_WAIT:
            summary = "Штатное безопасное ожидание падения напряжения при выключенном выходе."
            next_stage = self._safe_wait_next_stage or self.STAGE_MAIN
            transition = "Переход при падении до порога или по таймауту 2ч."
        elif self.current_stage == self.STAGE_COOLING:
            summary = "Пауза на охлаждение до безопасной температуры."
            next_stage = self._cooling_from_stage or self.STAGE_MAIN
            transition = "Возврат при T <= 35°C."
        elif self.current_stage == self.STAGE_DONE:
            summary = "Завершение/хранение."
            next_stage = self.STAGE_IDLE
            transition = "Активный заряд завершён."
        else:
            summary = "Idle."
            next_stage = self.STAGE_IDLE
            transition = "Активный заряд не идёт."

        safety = {
            "current_limit_a": MAX_STAGE_CURRENT,
            "ovp_offset_v": OVP_OFFSET,
            "ocp_offset_a": OCP_OFFSET,
            "temp_warning_c": TEMP_WARNING,
            "temp_pause_c": TEMP_PAUSE,
            "temp_critical_c": TEMP_CRITICAL,
            "safe_wait_margin_v": SAFE_WAIT_V_MARGIN,
            "safe_wait_max_sec": SAFE_WAIT_MAX_SEC,
            "watchdog_timeout_sec": WATCHDOG_TIMEOUT,
            "watchdog_high_v_sec": HIGH_V_FAST_TIMEOUT,
            "watchdog_high_v_threshold": HIGH_V_THRESHOLD,
        }

        return {
            "profile": self.battery_type,
            "stage": self.current_stage,
            "is_active": self.is_active,
            "target_voltage": target_v,
            "target_current": target_i,
            "timers": timers,
            "summary": summary,
            "transition": transition,
            "next_stage": next_stage,
            "hold": hold,
            "safety": safety,
            "agm_stage_idx": self._agm_stage_idx,
            "desulf_attempts": self.antisulfate_count,
            "finish_timer_active": self.finish_timer_start is not None,
            "session_reason": self._session_start_reason,
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
        return min(MAX_STAGE_CURRENT, max(0.1, pct * self.ah_capacity / 100.0))

    def _prep_target(self) -> Tuple[float, float]:
        return (12.0, 0.5)

    def _main_target(self) -> Tuple[float, float]:
        """v2.0: Main Charge — I_target = ah * 0.1 (ёмкостно-ориентированный расчёт)."""
        if self.battery_type == self.PROFILE_CUSTOM:
            return (self._custom_main_voltage, min(MAX_STAGE_CURRENT, self._custom_main_current))
        i_main = min(MAX_STAGE_CURRENT, self.ah_capacity * 0.1)  # 7.2A для 72Ah
        if self.battery_type == self.PROFILE_CA:
            return (14.7, i_main)
        if self.battery_type == self.PROFILE_EFB:
            return (14.8, i_main)
        if self.battery_type == self.PROFILE_AGM:
            v = AGM_STAGES[min(self._agm_stage_idx, len(AGM_STAGES) - 1)]
            return (v, i_main)
        return (14.7, i_main)

    def _desulf_target(self) -> Tuple[float, float]:
        return (16.3, self._pct_ah(2.0))

    def _mix_target(self) -> Tuple[float, float]:
        """v2.0: Mix Mode — I_target = ah * 0.03 (ёмкостно-ориентированный расчёт)."""
        i_mix = min(MAX_STAGE_CURRENT, self.ah_capacity * 0.03)  # 2.16A для 72Ah
        if self.battery_type == self.PROFILE_AGM:
            return (16.3, i_mix)
        return (16.5, i_mix)

    def _storage_target(self) -> Tuple[float, float]:
        return (13.8, 1.0)
    
    def _get_current_targets(self) -> Tuple[float, float]:
        """Получить текущие целевые параметры V/I в зависимости от этапа."""
        if self.current_stage == self.STAGE_MAIN:
            return self._main_target()
        elif self.current_stage == self.STAGE_DESULFATION:
            return self._desulf_target()
        elif self.current_stage == self.STAGE_MIX:
            return self._mix_target()
        else:
            return (14.0, 1.0)  # безопасные значения по умолчанию

    def _check_temp_safety(
        self,
        temp: float,
        voltage: float,
        current: float,
        ah_charged: float,
        stage_duration_min: float,
    ) -> Optional[str]:
        """
        Проверка температуры. ВАЖНО: temp должен быть ТОЛЬКО с внешнего датчика АКБ (sensor.rd_6018_temperature_external).
        Аварийная остановка 45°C — только по внешнему датчику. Внутренняя температура БП не используется для защиты АКБ.
        """
        if temp >= TEMP_CRITICAL:
            return (
                "🔴 <b>АВАРИЙНОЕ ОТКЛЮЧЕНИЕ (ПЕРЕГРЕВ АКБ)</b>\n\n"
                f"Температура (внешний датчик): <code>{temp:.1f}</code>°C (порог {TEMP_CRITICAL:.0f}°C)\n"
                f"Текущий этап: <code>{self.current_stage}</code>\n"
                f"Напряжение: <code>{voltage:.2f}</code>В\n"
                f"Ток: <code>{current:.2f}</code>А\n"
                f"Накопленная ёмкость: <code>{ah_charged:.2f}</code> Ач\n"
                f"Время в текущем режиме: <code>{stage_duration_min:.0f}</code> мин."
            )
        if temp >= TEMP_WARNING and not self._temp_warning_alerted:
            self._temp_warning_alerted = True
            self._pending_log_event = "WARNING_35C"
            self.notify(
                f"⚠️ Внимание: Температура АКБ поднялась до {temp:.1f}°C. "
                f"При {TEMP_PAUSE}°C заряд будет приостановлен."
            )
        return None

    def _detect_stuck_current(self, current: float) -> bool:
        """Застревание тока выше порога — триггер десульфации (0.2А для AGM, 0.3А для Ca/EFB)."""
        threshold = DESULF_CURRENT_STUCK_AGM if self.battery_type == self.PROFILE_AGM else DESULF_CURRENT_STUCK
        return current > threshold

    def _track_stuck_current_plateau(self, now: float, current: float, threshold: float) -> Optional[int]:
        """Отслеживать полку тока выше порога; новый минимум сбрасывает таймер."""
        if current < threshold:
            self._stuck_current_since = None
            self._stuck_current_value = None
            return None

        if self._stuck_current_since is None or self._stuck_current_value is None:
            self._stuck_current_since = now
            self._stuck_current_value = current
            return 0

        if current < self._stuck_current_value:
            self._stuck_current_since = now
            self._stuck_current_value = current
            return 0

        return int((now - self._stuck_current_since) / 60)

    def _sync_hold_minimum(self, now: float, current: float, threshold: float) -> None:
        if current >= threshold:
            self._first_stage_hold_since = None
            self._first_stage_hold_current = None
            return

        if self._first_stage_hold_current is None or current < self._first_stage_hold_current:
            self._first_stage_hold_since = now
            self._first_stage_hold_current = current

    def _exit_cc_condition(self, v_now: float) -> bool:
        """Выход CC: V упало на дельту от пика."""
        if self.v_max_recorded is None:
            return False
        delta_v = self._custom_delta_threshold if self.battery_type == self.PROFILE_CUSTOM else DELTA_V_EXIT
        return v_now <= self.v_max_recorded - delta_v

    def _exit_cv_condition(self, i_now: float) -> bool:
        """Выход CV: I выросло на дельту от минимума."""
        if self.i_min_recorded is None:
            return False
        delta_i = self._custom_delta_threshold if self.battery_type == self.PROFILE_CUSTOM else DELTA_I_EXIT
        return i_now >= self.i_min_recorded + delta_i

    def _get_stage_max_hours(self) -> Optional[float]:
        """Макс. часов этапа для прогресс-репорта, или None если нет лимита."""
        if self.current_stage == self.STAGE_DESULFATION:
            return 2.0
        if self.current_stage == self.STAGE_MIX:
            if self.finish_timer_start is not None:
                return 2.0  # таймер 2ч после Delta
            if self.battery_type == self.PROFILE_EFB:
                return float(EFB_MIX_MAX_HOURS)
            if self.battery_type == self.PROFILE_CA:
                return float(CA_MIX_MAX_HOURS)
            if self.battery_type == self.PROFILE_AGM:
                return float(AGM_MIX_MAX_HOURS)
            return 2.0
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

    def _make_log_event_end(
        self,
        now: float,
        ah: float,
        voltage: float,
        current: float,
        temp: float,
        trigger: str,
    ) -> Dict[str, Any]:
        """Сформировать данные для лога завершения текущего этапа (до смены current_stage)."""
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

    async def tick(
        self,
        voltage: float,
        current: float,
        temp_ext: Optional[float],
        is_cv: bool,
        ah: float,
        output_is_on: Optional[Any] = None,
        manual_off_active: bool = False,
    ) -> Dict[str, Any]:
        """
        Основной цикл. Вызывается из фоновой задачи каждые 30 сек.
        Возвращает dict: set_voltage, set_current, turn_off, notify, emergency_stop.

        output_is_on — последнее известное состояние выхода (on/off); при unavailable
        по нему решаем, слать ли критическое уведомление или тихо перейти в IDLE.
        manual_off_active — задано условие «off»: часовые отчёты этапа не шлём.

        ВАЖНО: voltage — ВСЕГДА sensor.rd_6018_battery_voltage (напряжение на клеммах АКБ).
        Используется для расчёта дельты (спад 0.03В) и порогов перехода фаз.
        """
        actions: Dict[str, Any] = {}
        now = time.time()
        self.last_update_time = now

        if temp_ext is None or temp_ext in ("unavailable", "unknown", ""):
            self._was_unavailable = True
            self._link_lost_at = now  # время последней потери связи для коррекции таймеров при восстановлении
            actions["emergency_stop"] = True
            actions["log_event"] = "EMERGENCY_UNAVAILABLE"
            if self._last_known_output_on:
                # Связь потеряна во время активного заряда: аварийно останавливаем,
                # но не чистим файл сессии, чтобы можно было восстановиться после возврата связи.
                msg = "⚠️ Связь потеряна во время заряда!"
                actions["notify"] = msg
                self.notify(msg)
                if self.is_active:
                    self.stop(clear_session=False)
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

        # Трехуровневая температурная защита
        if temp >= TEMP_CRITICAL:
            # 45°C - критическая температура: полный сброс в IDLE
            mode_text = "ручном режиме" if self.battery_type == self.PROFILE_CUSTOM else "режиме"
            msg = (
                f"🔴 <b>КРИТИЧЕСКИЙ ПЕРЕГРЕВ в {mode_text}!</b>\n"
                f"Температура: {temp:.1f}°C (критическая: {TEMP_CRITICAL}°C)\n"
                "Заряд экстренно остановлен и сброшен!"
            )
            actions["emergency_stop"] = True
            actions["full_reset"] = True
            actions["notify"] = msg
            actions["log_event"] = f"EMERGENCY_TEMP_CRITICAL: {temp:.1f}°C >= {TEMP_CRITICAL}°C"
            self.notify(msg)
            return actions
        
        elif temp >= TEMP_PAUSE and self.current_stage not in (self.STAGE_COOLING, self.STAGE_IDLE, self.STAGE_DONE):
            # 40°C - пауза заряда: переход в режим охлаждения
            actions["log_event_end"] = self._make_log_event_end(
                now, ah, voltage, current, temp, f"T≥{TEMP_PAUSE}°C ({temp:.1f}°C)"
            )
            cooling_target_v, cooling_target_i = self._get_current_targets()
            prev_stage = self.current_stage
            self.current_stage = self.STAGE_COOLING
            self._clear_restored_targets()
            self.stage_start_time = now
            self._stage_start_ah = ah
            self._cooling_from_stage = prev_stage
            self._cooling_target_v, self._cooling_target_i = cooling_target_v, cooling_target_i
            
            msg = (
                f"🌡 <b>ПЕРЕГРЕВ - ПАУЗА ЗАРЯДА!</b>\n"
                f"Температура: {temp:.1f}°C (лимит: {TEMP_PAUSE}°C)\n"
                f"Выход отключен. Ожидание охлаждения до {TEMP_WARNING}°C."
            )
            actions["turn_off"] = True
            actions["notify"] = msg
            actions["log_event"] = "START"
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
            actions["log_event"] = "EMERGENCY_TEMP_45C"
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

        report_interval = STORAGE_REPORT_INTERVAL_SEC if (
            voltage < 14.0 and self.current_stage in (self.STAGE_SAFE_WAIT, self.STAGE_DONE)
        ) else 3600
        if not manual_off_active and now - self._last_hourly_report >= report_interval:
            self._last_hourly_report = now
            current_hrs = elapsed / 3600.0
            max_hrs = self._get_stage_max_hours()
            max_str = f"{max_hrs:.0f}" if max_hrs is not None else "—"
            report = (
                f"⏳ Прошло {current_hrs:.1f}ч из {max_str} лимита этапа. "
                f"Ток: {current:.2f} А, T: {temp:.1f}°C, Ah: {ah:.2f}."
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

        # Инициализация ёмкости на входе в этап при первом тике (старт/восстановление) + лог старта этапа
        if self._stage_start_ah == 0 and self.current_stage in (
            self.STAGE_PREP, self.STAGE_MAIN, self.STAGE_DESULFATION, self.STAGE_MIX,
            self.STAGE_SAFE_WAIT, self.STAGE_COOLING,
        ):
            self._stage_start_ah = ah
            if "log_event" not in actions:
                profile_tag = "CUSTOM" if self.battery_type == self.PROFILE_CUSTOM else f"profile={self.battery_type}"
                actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah | {profile_tag}"

        # --- ПОДГОТОВКА (Soft Start) ---
        if self.current_stage == self.STAGE_PREP:
            uv, ui = self._prep_target()
            if voltage < 12.0:
                actions["set_voltage"] = uv
                actions["set_current"] = ui
            else:
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"V≥12В ({voltage:.2f}В)"
                )
                prev = self.current_stage
                self.current_stage = self.STAGE_MAIN
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                self._start_ah = ah
                self._reset_delta_and_blanking(now)
                _log_trigger(prev, self.current_stage, "V_threshold", f"Факт: {voltage:.2f}В >= 12.0В")
                uv, ui = self._main_target()
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["notify"] = (
                    "<b>✅ Фаза завершена:</b> Подготовка\n"
                    "<b>🚀 Переход к:</b> Main Charge"
                )
                actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"

        # --- MAIN CHARGE ---
        elif self.current_stage == self.STAGE_MAIN:
            uv, ui = self._get_target_v_i()  # после restore — уставки из сессии, иначе по профилю
            in_blanking = now < self._blanking_until

            # Защитный лимит времени MAIN (72ч авто, пользовательский для CUSTOM)
            # При заданном условии «off» таймер режима не срабатывает — выключение только по off.
            stage_elapsed_hours = (now - self.stage_start_time) / 3600.0
            max_hours = self._custom_time_limit_hours if self.battery_type == self.PROFILE_CUSTOM else MAIN_STAGE_MAX_HOURS
            if not manual_off_active and stage_elapsed_hours >= max_hours:
                prev = self.current_stage
                transition_threshold = DESULF_CURRENT_STUCK_AGM if self.battery_type == self.PROFILE_AGM else DESULF_CURRENT_STUCK
                force_mix_on_timeout = self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB)
                can_mix_by_threshold = self.battery_type != self.PROFILE_CUSTOM and is_cv and current <= transition_threshold
                if force_mix_on_timeout or can_mix_by_threshold:
                    timeout_reason = (
                        f"Лимит {max_hours}ч, принудительный переход в MIX для {self.battery_type}"
                        if force_mix_on_timeout
                        else f"Лимит {max_hours}ч, I<={transition_threshold}A"
                    )
                    actions["log_event_end"] = self._make_log_event_end(
                        now, ah, voltage, current, temp, timeout_reason
                    )
                    self.current_stage = self.STAGE_MIX
                    self._clear_restored_targets()
                    self.stage_start_time = now
                    self._stage_start_ah = ah
                    self._reset_delta_and_blanking(now)
                    if force_mix_on_timeout:
                        _log_trigger(prev, self.current_stage, "TIME_LIMIT_MAIN_TO_MIX_FORCE", f"Limit {max_hours}h reached for {self.battery_type}, forced MIX")
                    else:
                        _log_trigger(prev, self.current_stage, "TIME_LIMIT_MAIN_TO_MIX", f"Limit {max_hours}h, I={current:.2f}A <= {transition_threshold}A")
                    mxv, mxi = self._mix_target()
                    actions["set_voltage"] = mxv
                    actions["set_current"] = mxi
                    self._add_phase_limits(actions, mxv, mxi)
                    if force_mix_on_timeout:
                        actions["notify"] = (
                            f"<b>⏱ Лимит {max_hours}ч MAIN.</b> "
                            "<b>Переход к:</b> Mix Mode по правилу тайм-лимита профиля."
                        )
                    else:
                        actions["notify"] = (
                            f"<b>⏱ Лимит {max_hours}ч MAIN.</b> Ток перехода достиг (I≤{transition_threshold}А). "
                            "<b>Переход к:</b> Mix Mode."
                        )
                    actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"
                else:
                    actions["log_event_end"] = self._make_log_event_end(
                        now, ah, voltage, current, temp, f"Лимит времени {max_hours}ч"
                    )
                    self.current_stage = self.STAGE_DONE
                    self._clear_restored_targets()
                    self.stage_start_time = now
                    self._stage_start_ah = ah
                    self._blanking_until = now + BLANKING_SEC
                    self._delta_trigger_count = 0
                    trigger_name = "TIME_LIMIT"
                    condition = f"Достигнут лимит {max_hours}ч для этапа MAIN"
                    _log_trigger(prev, self.current_stage, trigger_name, condition)
                    actions["turn_off"] = True
                    mode_text = "ручном режиме" if self.battery_type == self.PROFILE_CUSTOM else "автоматическом режиме"
                    actions["notify"] = (
                        "<b>🛑 ЛИМИТ ВРЕМЕНИ ДОСТИГНУТ!</b>\n"
                        f"Этап MAIN длился {stage_elapsed_hours:.1f}ч (лимит {max_hours}ч)\n"
                        f"Заряд в {mode_text} завершен. Проверьте состояние АКБ."
                    )
                    actions["log_event"] = "START"
                    self._clear_session_file()
                return actions

            # Ручной режим: используем только дельта-триггер для завершения (v2.0: мониторинг только после 120 сек)
            if self.battery_type == self.PROFILE_CUSTOM:
                if now >= self._delta_monitor_after:
                    if self.v_max_recorded is None or voltage > self.v_max_recorded:
                        self.v_max_recorded = voltage
                    if self.i_min_recorded is None or current < self.i_min_recorded:
                        self.i_min_recorded = current
                if now >= self._delta_monitor_after and not in_blanking and self._check_delta_finish(voltage, current):
                    if now - self._last_delta_confirm_time >= TRIGGER_CONFIRM_INTERVAL_SEC:
                        self._last_delta_confirm_time = now
                        self._delta_trigger_count += 1
                    if self._delta_trigger_count >= TRIGGER_CONFIRM_COUNT:
                        # Подтверждённый триггер - завершаем заряд
                        delta_v = self.v_max_recorded - voltage if self.v_max_recorded else 0
                        delta_i = current - self.i_min_recorded if self.i_min_recorded else 0
                        trigger_desc = f"dV={delta_v:.3f}В, dI={delta_i:.3f}А"
                        actions["log_event_end"] = self._make_log_event_end(
                            now, ah, voltage, current, temp, trigger_desc
                        )
                        prev = self.current_stage
                        self.current_stage = self.STAGE_DONE
                        self._clear_restored_targets()
                        self.stage_start_time = now
                        self._stage_start_ah = ah
                        self._blanking_until = now + BLANKING_SEC
                        self._delta_trigger_count = 0
                        
                        trigger_name = "CUSTOM_DELTA_TRIGGER"
                        condition = f"V_max={self.v_max_recorded:.3f}В, V_now={voltage:.3f}В, dV={delta_v:.3f}В, I_min={self.i_min_recorded:.3f}А, I_now={current:.3f}А, dI={delta_i:.3f}А. Порог: {self._custom_delta_threshold:.3f}. Подтверждено {TRIGGER_CONFIRM_COUNT}/{TRIGGER_CONFIRM_COUNT}"
                        _log_trigger(prev, self.current_stage, trigger_name, condition)
                        
                        actions["turn_off"] = True
                        actions["notify"] = (
                            "<b>✅ Ручной режим завершен!</b>\n"
                            f"Дельта-триггер сработал: {delta_v:.3f}В / {delta_i:.3f}А\n"
                            f"Порог: {self._custom_delta_threshold:.3f}"
                        )
                        actions["log_event"] = "START"
                        self._clear_session_file()
                        return actions
                    else:
                        # Триггер в процессе подтверждения
                        logger.info("CUSTOM: delta trigger %d/%d, waiting for confirmation", 
                                  self._delta_trigger_count, TRIGGER_CONFIRM_COUNT)
                else:
                    self._delta_trigger_count = 0
            
            elif self.battery_type == self.PROFILE_AGM:
                # На всех ступенях до 15В и перед MAIN->MIX: ток <0.2А в течение 2ч без нового минимума
                if not in_blanking:
                    self._sync_hold_minimum(now, current, DESULF_CURRENT_STUCK_AGM)
                if not in_blanking and is_cv and current >= DESULF_CURRENT_STUCK_AGM:
                    self._first_stage_hold_since = None
                    self._first_stage_hold_current = None
                if not in_blanking and is_cv and current < 0.2:
                    self._stuck_current_since = None
                    self._stuck_current_value = None
                    # Новый минимум тока — перезапуск 2ч; переход только после 2ч без нового минимума
                    if self._first_stage_hold_current is None or current < self._first_stage_hold_current:
                        self._first_stage_hold_since = now
                        self._first_stage_hold_current = current
                    hold_elapsed = now - self._first_stage_hold_since
                    if hold_elapsed >= AGM_FIRST_STAGE_HOLD_SEC:
                        self._first_stage_hold_since = None
                        self._first_stage_hold_current = None
                        if self._agm_stage_idx < len(AGM_STAGES) - 1:
                            self._agm_stage_idx += 1
                            self.stage_start_time = now
                            self._stage_start_ah = ah
                            self._reset_delta_and_blanking(now)
                            uv, ui = self._main_target()
                            _log_trigger(self.STAGE_MAIN, self.STAGE_MAIN, "AGM_stage_2h_hold", f"Ступень {self._agm_stage_idx + 1}/4: ток <0.2А {AGM_FIRST_STAGE_HOLD_HOURS}ч")
                            actions["set_voltage"] = uv
                            actions["set_current"] = ui
                            self._add_phase_limits(actions, uv, ui)
                            actions["notify"] = (
                                f"<b>🚀 AGM ступень {self._agm_stage_idx + 1}/4:</b> "
                                f"{uv:.1f}V (ток &lt;0.2А {AGM_FIRST_STAGE_HOLD_HOURS}ч)"
                            )
                            actions["log_event"] = f"└ AGM ступень {self._agm_stage_idx + 1}/4"
                        else:
                            phantom_note = ""
                            if elapsed < PHANTOM_CHARGE_MINUTES * 60 and not self._phantom_alerted:
                                self._phantom_alerted = True
                                phantom_note = (
                                    "\n\n<b>⚠️ Внимание:</b> Подозрительно быстрый заряд (ток упал за "
                                    f"{PHANTOM_CHARGE_MINUTES} мин). Возможна высокая сульфатация или потеря ёмкости."
                                )
                                actions["log_event_sub"] = "└ Подозрительно быстрый заряд (PHANTOM)"
                            actions["log_event_end"] = self._make_log_event_end(
                                now, ah, voltage, current, temp, f"I<0.2А {AGM_FIRST_STAGE_HOLD_HOURS}ч"
                            )
                            prev = self.current_stage
                            self.current_stage = self.STAGE_MIX
                            self._clear_restored_targets()
                            self.stage_start_time = now
                            self._stage_start_ah = ah
                            self._reset_delta_and_blanking(now)
                            _log_trigger(prev, self.current_stage, "I_drop_2h_hold", f"Факт: {current:.2f}А, выдержка {AGM_FIRST_STAGE_HOLD_HOURS}ч")
                            mxv, mxi = self._mix_target()
                            actions["set_voltage"] = mxv
                            actions["set_current"] = mxi
                            self._add_phase_limits(actions, mxv, mxi)
                            actions["notify"] = (
                                "<b>✅ Фаза завершена:</b> Main Charge\n"
                                f"<b>🚀 Переход к:</b> Mix Mode (ток &lt;0.2А {AGM_FIRST_STAGE_HOLD_HOURS}ч)"
                                f"{phantom_note}"
                            )
                            actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"
                else:
                    # AGM: застревание I >= 0.2А 40 мин — десульфация (макс 4 итерации)
                    if not in_blanking and is_cv and current >= DESULF_CURRENT_STUCK_AGM:
                        stuck_mins = self._track_stuck_current_plateau(now, current, DESULF_CURRENT_STUCK_AGM) or 0
                        if self.antisulfate_count < ANTISULFATE_MAX_AGM and stuck_mins >= DESULF_STUCK_MIN_MINUTES:
                            self.antisulfate_count += 1
                            self._stuck_current_since = None
                            self._stuck_current_value = None
                            actions["log_event_end"] = self._make_log_event_end(
                                now, ah, voltage, current, temp, f"I≥0.2А {stuck_mins}мин, десульфация #{self.antisulfate_count}"
                            )
                            prev = self.current_stage
                            self.current_stage = self.STAGE_DESULFATION
                            self._clear_restored_targets()
                            self.stage_start_time = now
                            self._stage_start_ah = ah
                            self._reset_delta_and_blanking(now)
                            _log_trigger(prev, self.current_stage, "AGM_I_stuck_0.2A", f"Факт: {current:.2f}А в течение {stuck_mins}мин, попытка #{self.antisulfate_count}")
                            dv, di = self._desulf_target()
                            actions["set_voltage"] = dv
                            actions["set_current"] = di
                            self._add_phase_limits(actions, dv, di)
                            actions["notify"] = (
                                f"🔧 <b>AGM Десульфатация #{self.antisulfate_count}</b>\n\n"
                                f"Ток застрял ≥ <code>{DESULF_CURRENT_STUCK_AGM}</code>А более <code>{stuck_mins}</code> мин. "
                                f"<code>{dv:.1f}</code>В / <code>{di:.2f}</code>А на 2 ч."
                            )
                            actions["log_event"] = "START"
                        elif self.antisulfate_count >= ANTISULFATE_MAX_AGM and stuck_mins >= DESULF_STUCK_MIN_MINUTES:
                            self._stuck_current_since = None
                            self._stuck_current_value = None
                            # Лимит десульфаций исчерпан — остаёмся в MAIN, переход в Mix по правилу 2ч на минимуме тока

            elif self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB):
                # Ca/EFB: застревание I >= 0.3А 40 мин -> десульфатация (макс 3 итерации).
                # После исчерпания лимита десульфации уходим в MIX по лимиту времени "полки" тока.
                if not in_blanking and is_cv and current >= DESULF_CURRENT_STUCK:
                    stuck_mins = self._track_stuck_current_plateau(now, current, DESULF_CURRENT_STUCK) or 0
                    if self.antisulfate_count < ANTISULFATE_MAX_CA_EFB and stuck_mins >= DESULF_STUCK_MIN_MINUTES:
                        self.antisulfate_count += 1
                        self._stuck_current_since = None
                        self._stuck_current_value = None
                        actions["log_event_end"] = self._make_log_event_end(
                            now, ah, voltage, current, temp, f"I>=0.3A {stuck_mins}min, desulf #{self.antisulfate_count}"
                        )
                        prev = self.current_stage
                        self.current_stage = self.STAGE_DESULFATION
                        self._clear_restored_targets()
                        self.stage_start_time = now
                        self._stage_start_ah = ah
                        self._reset_delta_and_blanking(now)
                        _log_trigger(
                            prev,
                            self.current_stage,
                            "CA_EFB_I_stuck_0.3A",
                            f"Факт: {current:.2f}А в течение {stuck_mins} мин, попытка #{self.antisulfate_count}",
                        )
                        dv, di = self._desulf_target()
                        actions["set_voltage"] = dv
                        actions["set_current"] = di
                        self._add_phase_limits(actions, dv, di)
                        actions["notify"] = (
                            f"🔧 <b>{self.battery_type}: десульфатация #{self.antisulfate_count}</b>\n\n"
                            f"Ток держится на уровне <code>{DESULF_CURRENT_STUCK:.1f}А</code> и выше уже "
                            f"<code>{stuck_mins}</code> мин.\n"
                            f"Запускаю этап десульфатации: <code>{dv:.1f}В</code> / <code>{di:.2f}А</code> "
                            f"на <code>2 часа</code>."
                        )
                        actions["log_event"] = "START"
                    elif self.antisulfate_count >= ANTISULFATE_MAX_CA_EFB and stuck_mins >= MAIN_MIX_STUCK_CV_MIN:
                        self._stuck_current_since = None
                        self._stuck_current_value = None
                        actions["log_event_end"] = self._make_log_event_end(
                            now, ah, voltage, current, temp, f"I>=0.3A {stuck_mins}min, desulf limit -> MIX"
                        )
                        prev = self.current_stage
                        self.current_stage = self.STAGE_MIX
                        self._clear_restored_targets()
                        self.stage_start_time = now
                        self._stage_start_ah = ah
                        self._reset_delta_and_blanking(now)
                        _log_trigger(prev, self.current_stage, "CA_EFB_desulf_limit_to_MIX", f"I={current:.2f}A stuck for {stuck_mins}min, desulf limit reached")
                        mxv, mxi = self._mix_target()
                        actions["set_voltage"] = mxv
                        actions["set_current"] = mxi
                        self._add_phase_limits(actions, mxv, mxi)
                        actions["notify"] = (
                            f"<b>⏱ Достигнут лимит циклов десульфатации ({ANTISULFATE_MAX_CA_EFB}).</b> "
                            f"Переход в Mix Mode после {stuck_mins} мин повышенного тока в CV."
                        )
                        actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"
                else:
                    self._stuck_current_since = None
                    self._stuck_current_value = None

            # Переход MAIN->MIX по падению тока: Ca/EFB — ждём 3ч на минимуме <0.3А; AGM — в блоке PROFILE_AGM
            if self.battery_type in (self.PROFILE_CA, self.PROFILE_EFB):
                if not in_blanking:
                    self._sync_hold_minimum(now, current, DESULF_CURRENT_STUCK)
                if not in_blanking and is_cv and current >= 0.3:
                    self._first_stage_hold_since = None
                    self._first_stage_hold_current = None
                elif not in_blanking and is_cv and current < 0.3:
                    self._stuck_current_since = None
                    self._stuck_current_value = None
                    # Новый минимум тока — перезапуск 3ч; переход только после 3ч без нового минимума
                    if self._first_stage_hold_current is None or current < self._first_stage_hold_current:
                        self._first_stage_hold_since = now
                        self._first_stage_hold_current = current
                    hold_elapsed = now - self._first_stage_hold_since
                    if hold_elapsed >= FIRST_STAGE_HOLD_SEC:
                        self._first_stage_hold_since = None
                        self._first_stage_hold_current = None
                        phantom_note = ""
                        if elapsed < PHANTOM_CHARGE_MINUTES * 60 and not self._phantom_alerted:
                            self._phantom_alerted = True
                            phantom_note = (
                                "\n\n<b>⚠️ Внимание:</b> Подозрительно быстрый заряд (ток упал за "
                                f"{PHANTOM_CHARGE_MINUTES} мин). Возможна высокая сульфатация или потеря ёмкости."
                            )
                            actions["log_event_sub"] = "└ Подозрительно быстрый заряд (PHANTOM)"
                        actions["log_event_end"] = self._make_log_event_end(
                            now, ah, voltage, current, temp, f"I<0.3А {FIRST_STAGE_HOLD_HOURS}ч"
                        )
                        prev = self.current_stage
                        self.current_stage = self.STAGE_MIX
                        self._clear_restored_targets()
                        self.stage_start_time = now
                        self._stage_start_ah = ah
                        self._reset_delta_and_blanking(now)
                        _log_trigger(prev, self.current_stage, "I_drop_3h_hold", f"Факт: {current:.2f}А, выдержка {FIRST_STAGE_HOLD_HOURS}ч")
                        mxv, mxi = self._mix_target()
                        actions["set_voltage"] = mxv
                        actions["set_current"] = mxi
                        self._add_phase_limits(actions, mxv, mxi)
                        actions["notify"] = (
                            "<b>✅ Фаза завершена:</b> Main Charge\n"
                            f"<b>🚀 Переход к:</b> Mix Mode (ток &lt;0.3А {FIRST_STAGE_HOLD_HOURS}ч)"
                            f"{phantom_note}"
                        )
                        actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"

        # --- БЕЗОПАСНОЕ ОЖИДАНИЕ (Output OFF, ждём падения V) ---
        elif self.current_stage == self.STAGE_SAFE_WAIT:
            if now - self._last_safe_wait_sample >= 300:
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
            threshold = self._safe_wait_target_v - SAFE_WAIT_V_MARGIN
            wait_elapsed = now - self._safe_wait_start
            if voltage <= threshold:
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"V≤{threshold:.1f}В ({voltage:.2f}В)"
                )
                prev = self.STAGE_SAFE_WAIT
                next_stage = self._safe_wait_next_stage or self.STAGE_MAIN
                self.current_stage = next_stage
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                uv, ui = self._safe_wait_target_v, self._safe_wait_target_i
                self._safe_wait_next_stage = None
                _log_trigger(prev, self.current_stage, "V_drop_threshold", f"Факт: {voltage:.2f}В <= {threshold:.1f}В")
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
                    actions["log_event"] = "START"
                    self._clear_session_file()
                else:
                    self.v_max_recorded = None
                    self.i_min_recorded = None
                    self._blanking_until = now + BLANKING_SEC
                    self._delta_trigger_count = 0
                    actions["notify"] = "<b>🚀 Возврат к Main Charge.</b> Напряжение упало."
                    actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"
            elif wait_elapsed >= SAFE_WAIT_MAX_SEC:
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"Таймаут 2ч (V не упало)"
                )
                prev = self.STAGE_SAFE_WAIT
                next_stage = self._safe_wait_next_stage or self.STAGE_MAIN
                self.current_stage = next_stage
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                uv, ui = self._safe_wait_target_v, self._safe_wait_target_i
                self._safe_wait_next_stage = None
                _log_trigger(prev, self.current_stage, "Safe_wait_timeout", f"Таймер: {wait_elapsed/3600:.1f}ч >= 2ч")
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["turn_on"] = True
                self._blanking_until = now + BLANKING_SEC
                actions["notify"] = (
                    "⚠️ Напряжение падает слишком медленно, возможен сильный нагрев или дефект АКБ. "
                    f"Принудительный переход к следующему этапу ({uv:.1f}В)."
                )
                actions["log_event"] = "START"
                if self.current_stage == self.STAGE_DONE:
                    self._clear_session_file()
                else:
                    self.v_max_recorded = None
                    self.i_min_recorded = None
                    self._blanking_until = now + BLANKING_SEC
                    self._delta_trigger_count = 0
            else:
                pass  # продолжаем ждать

        # --- ОХЛАЖДЕНИЕ ---
        elif self.current_stage == self.STAGE_COOLING:
            # Проверяем, остыла ли АКБ до безопасной температуры
            if temp <= TEMP_WARNING:
                # Температура упала до 35°C - можно возвращаться к заряду
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"T≤{TEMP_WARNING}°C ({temp:.1f}°C)"
                )
                prev_stage = self.current_stage
                return_stage = self._cooling_from_stage or self.STAGE_MAIN
                self.current_stage = return_stage
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                
                # Восстанавливаем целевые параметры
                uv, ui = self._cooling_target_v, self._cooling_target_i
                self._cooling_from_stage = None
                
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["turn_on"] = True
                self._blanking_until = now + BLANKING_SEC
                
                msg = (
                    f"🌡 <b>АКБ ОСТЫЛА - ВОЗВРАТ К ЗАРЯДУ!</b>\n"
                    f"Температура: {temp:.1f}°C (норма: ≤{TEMP_WARNING}°C)\n"
                    f"Возврат к этапу: {return_stage}"
                )
                actions["notify"] = msg
                actions["log_event"] = f"START | Емкость: {self.ah_capacity}Ah"
                self.notify(msg)
            else:
                # Продолжаем ждать охлаждения
                pass

        # --- ДЕСУЛЬФАТАЦИЯ ---
        elif self.current_stage == self.STAGE_DESULFATION:
            if elapsed >= 2 * 3600:
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, "Таймер 2ч"
                )
                prev = self.current_stage
                uv, ui = self._main_target()
                threshold = uv - SAFE_WAIT_V_MARGIN  # 14.2В при цели 14.7В
                self.current_stage = self.STAGE_SAFE_WAIT
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                self._safe_wait_next_stage = self.STAGE_MAIN
                self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                self._safe_wait_start = now
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
                _log_trigger(prev, self.STAGE_SAFE_WAIT, "Desulf_timer_2h", f"Время: {elapsed/3600:.1f}ч >= 2ч")
                actions["turn_off"] = True
                actions["notify"] = (
                    f"<b>⏸ Десульфатация завершена.</b> Ожидание падения до {threshold:.1f}В. "
                    "Выход выключен."
                )
                actions["log_event"] = "START"

        # --- MIX MODE ---
        elif self.current_stage == self.STAGE_MIX:
            # v2.0: мониторинг dV/dI только через 120 сек после смены уставок (исключаем переходные процессы)
            if now < self._blanking_until or now < self._delta_monitor_after:
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
                            f"└ Дельта V: V_max={v_peak:.2f}В, dV={delta_v:.3f}В"
                        )
                    elif self._exit_cv_condition(current):
                        delta_i = current - i_min
                        actions["log_event"] = (
                            f"└ Дельта I: I_min={i_min:.2f}А, dI={delta_i:.3f}А"
                        )
                    else:
                        actions["log_event"] = f"└ {trigger_msg[:50]}"
                if self.finish_timer_start and (now - self.finish_timer_start) >= MIX_DONE_TIMER:
                    v_peak = self.v_max_recorded or voltage
                    i_min = self.i_min_recorded or current
                    trigger_desc = "Таймер 2ч после Delta"
                    if self._exit_cc_condition(voltage):
                        trigger_desc = f"ΔV≥{DELTA_V_EXIT}В, V_max={v_peak:.2f}В"
                    elif self._exit_cv_condition(current) and i_min is not None:
                        trigger_desc = f"ΔI≥{DELTA_I_EXIT}А, I_min={i_min:.2f}А"
                    actions["log_event_end"] = self._make_log_event_end(
                        now, ah, voltage, current, temp, trigger_desc
                    )
                    prev = self.current_stage
                    uv, ui = self._storage_target()
                    threshold = uv - SAFE_WAIT_V_MARGIN  # 13.3В
                    self.current_stage = self.STAGE_SAFE_WAIT
                    self._clear_restored_targets()
                    self.stage_start_time = now
                    self._stage_start_ah = ah
                    self._safe_wait_next_stage = self.STAGE_DONE
                    self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                    self._safe_wait_start = now
                    self._safe_wait_v_samples.append((now, voltage))
                    self._last_safe_wait_sample = now
                    delta_log = ""
                    if self._exit_cc_condition(voltage):
                        delta_log = f" V_max было {v_peak:.2f}В, закончили на {voltage:.2f}В. Дельта {DELTA_V_EXIT}В достигнута."
                    elif self._exit_cv_condition(current) and i_min is not None:
                        delta_log = f" I_min было {i_min:.2f}А, текущий {current:.2f}А. Дельта {DELTA_I_EXIT}А достигнута."
                    _log_trigger(prev, self.STAGE_SAFE_WAIT, "Mix_timer_2h", f"Время после Delta: {(now - self.finish_timer_start)/3600:.1f}ч >= 2ч.{delta_log}")
                    actions["turn_off"] = True
                    actions["notify"] = (
                        f"<b>✅ Таймер 2ч выполнен.</b> Ожидание падения до {threshold:.1f}В. "
                        f"V_max={self.v_max_recorded:.2f}В. Выход выключен."
                    )
                    actions["log_event"] = "START"
            elif not manual_off_active and self.battery_type == self.PROFILE_EFB and elapsed >= EFB_MIX_MAX_HOURS * 3600:
                v_peak = self.v_max_recorded or voltage
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"EFB лимит 10ч, V_max={v_peak:.2f}В"
                )
                prev = self.current_stage
                uv, ui = self._storage_target()
                threshold = uv - SAFE_WAIT_V_MARGIN
                self.current_stage = self.STAGE_SAFE_WAIT
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                self._safe_wait_next_stage = self.STAGE_DONE
                self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                self._safe_wait_start = now
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
                _log_trigger(prev, self.STAGE_SAFE_WAIT, "EFB_Mix_limit_10h", f"Время: {elapsed/3600:.1f}ч >= 10ч. V_max было {v_peak:.2f}В, закончили на {voltage:.2f}В.")
                actions["turn_off"] = True
                actions["notify"] = (
                    f"<b>⏱ EFB Mix:</b> лимит 10ч. Ожидание падения до {threshold:.1f}В. "
                    f"V_max={v_peak:.2f}В. Выход выключен."
                )
                actions["log_event"] = "START"
            elif not manual_off_active and self.battery_type == self.PROFILE_CA and elapsed >= CA_MIX_MAX_HOURS * 3600:
                v_peak = self.v_max_recorded or voltage
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"Ca/Ca лимит 8ч, V_max={v_peak:.2f}В"
                )
                prev = self.current_stage
                uv, ui = self._storage_target()
                threshold = uv - SAFE_WAIT_V_MARGIN
                self.current_stage = self.STAGE_SAFE_WAIT
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                self._safe_wait_next_stage = self.STAGE_DONE
                self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                self._safe_wait_start = now
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
                _log_trigger(prev, self.STAGE_SAFE_WAIT, "CA_Mix_limit_8h", f"Время: {elapsed/3600:.1f}ч >= 8ч. V_max было {v_peak:.2f}В, закончили на {voltage:.2f}В.")
                actions["turn_off"] = True
                actions["notify"] = (
                    f"<b>⏱ Ca/Ca Mix:</b> лимит 8ч. Ожидание падения до {threshold:.1f}В. V_max={v_peak:.2f}В."
                )
                actions["log_event"] = "START"
            elif not manual_off_active and self.battery_type == self.PROFILE_AGM and elapsed >= AGM_MIX_MAX_HOURS * 3600:
                v_peak = self.v_max_recorded or voltage
                actions["log_event_end"] = self._make_log_event_end(
                    now, ah, voltage, current, temp, f"AGM лимит 5ч, V_max={v_peak:.2f}В"
                )
                prev = self.current_stage
                uv, ui = self._storage_target()
                threshold = uv - SAFE_WAIT_V_MARGIN
                self.current_stage = self.STAGE_SAFE_WAIT
                self._clear_restored_targets()
                self.stage_start_time = now
                self._stage_start_ah = ah
                self._safe_wait_next_stage = self.STAGE_DONE
                self._safe_wait_target_v, self._safe_wait_target_i = uv, ui
                self._safe_wait_start = now
                self._safe_wait_v_samples.append((now, voltage))
                self._last_safe_wait_sample = now
                _log_trigger(prev, self.STAGE_SAFE_WAIT, "AGM_Mix_limit_5h", f"Время: {elapsed/3600:.1f}ч >= 5ч. V_max было {v_peak:.2f}В, закончили на {voltage:.2f}В.")
                actions["turn_off"] = True
                actions["notify"] = (
                    f"<b>⏱ AGM Mix:</b> лимит 5ч. Ожидание падения до {threshold:.1f}В. V_max={v_peak:.2f}В."
                )
                actions["log_event"] = "START"

        if "notify" in actions:
            self.notify(actions["notify"])

        if "log_event" in actions and not str(actions["log_event"]).strip().startswith("└"):
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
