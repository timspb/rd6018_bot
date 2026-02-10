"""
charge_logic.py — State Machine заряда для Ca/Ca, EFB, AGM.
Профили: Ca/Ca (Liquid), EFB, AGM с десульфатацией и Mix Mode.
Auto-Resume: сохранение сессии в charge_session.json, восстановление при перезапуске.
"""
import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import MAX_VOLTAGE

logger = logging.getLogger("rd6018")

SESSION_FILE = "charge_session.json"
SESSION_MAX_AGE = 60 * 60  # сек — восстанавливать только если последняя запись < 60 мин назад

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


class ChargeController:
    """
    Контроллер заряда с машиной состояний.
    Этапы: PОДГОТОВКА (Soft Start), Main (Bulk), Desulfation, Mix, Done.
    """

    STAGE_PREP = "Подготовка"
    STAGE_MAIN = "Main Charge"
    STAGE_DESULFATION = "Десульфатация"
    STAGE_MIX = "Mix Mode"
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
        self._clear_session_file()
        logger.info("ChargeController started: %s %dAh", battery_type, self.ah_capacity)

    def stop(self) -> None:
        """Остановка заряда."""
        prev = self.current_stage
        self.current_stage = self.STAGE_IDLE
        self.v_max_recorded = None
        self.i_min_recorded = None
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
        if self.current_stage == self.STAGE_DONE:
            return self._storage_target()
        return (0.0, 0.0)

    def _save_session(self, voltage: float, current: float, ah: float) -> None:
        """Сохранить текущее состояние в charge_session.json."""
        if self.current_stage == self.STAGE_IDLE or self.current_stage == self.STAGE_DONE:
            return
        target_finish = self._get_target_finish_time()
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

        target_finish = data.get("target_finish_time")
        target_v = float(data.get("target_voltage", 14.7))
        target_i = float(data.get("target_current", 1.0))

        now = time.time()
        self.finish_timer_start = data.get("finish_timer_start")

        if target_finish is not None:
            remaining_sec = target_finish - now
            if remaining_sec > 0:
                if self.current_stage == self.STAGE_DESULFATION:
                    phase_dur = 2 * 3600
                    self.stage_start_time = now - (phase_dur - remaining_sec)
                elif self.current_stage == self.STAGE_MIX and self.finish_timer_start is not None:
                    self.finish_timer_start = target_finish - MIX_DONE_TIMER
                else:
                    self.stage_start_time = now - (
                        (target_finish - data.get("stage_start_time", now)) - remaining_sec
                    )
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
            msg = (
                f"🔄 <b>Сессия восстановлена!</b>\n\n"
                f"Продолжаю режим: <code>{self.current_stage}</code>.\n"
                f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
            )

        self.v_max_recorded = None
        self.i_min_recorded = None
        self.finish_timer_start = None
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

    @property
    def is_active(self) -> bool:
        return self.current_stage != self.STAGE_IDLE

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
    ) -> Dict[str, Any]:
        """
        Основной цикл. Вызывается из фоновой задачи каждые 30 сек.
        Возвращает dict: set_voltage, set_current, turn_off, notify, emergency_stop.
        """
        actions: Dict[str, Any] = {}
        now = time.time()
        self.last_update_time = now

        if temp_ext is None or temp_ext in ("unavailable", "unknown", ""):
            msg = (
                "🔴 <b>АВАРИЯ:</b> Датчик температуры (sensor.rd_6018_temperature_external) "
                "выдаёт ошибку или Unavailable. Заряд остановлен в целях безопасности."
            )
            actions["emergency_stop"] = True
            actions["full_reset"] = True
            actions["notify"] = msg
            actions["log_event"] = "EMERGENCY_UNAVAILABLE"
            self.notify(msg)
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

        self.is_cv = is_cv

        # --- ПОДГОТОВКА (Soft Start) ---
        if self.current_stage == self.STAGE_PREP:
            uv, ui = self._prep_target()
            if voltage < 12.0:
                actions["set_voltage"] = uv
                actions["set_current"] = ui
            else:
                self.current_stage = self.STAGE_MAIN
                self.stage_start_time = now
                self._start_ah = ah
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

            if self.battery_type == self.PROFILE_AGM:
                stage_mins = elapsed / 60
                if self._agm_stage_idx < len(AGM_STAGES) - 1 and stage_mins >= AGM_STAGE_MIN_MINUTES:
                    self._agm_stage_idx += 1
                    self.stage_start_time = now
                    uv, ui = self._main_target()
                    actions["set_voltage"] = uv
                    actions["set_current"] = ui
                    self._add_phase_limits(actions, uv, ui)
                    actions["notify"] = (
                        f"<b>🚀 AGM ступень {self._agm_stage_idx + 1}/4:</b> "
                        f"{uv:.1f}V"
                    )
                    actions["log_event"] = f"AGM_STAGE_{self._agm_stage_idx + 1}/4"
                else:
                    if is_cv and current < 0.2:
                        self.current_stage = self.STAGE_MIX
                        self.stage_start_time = now
                        self.v_max_recorded = voltage
                        self.i_min_recorded = current
                        mxv, mxi = self._mix_target()
                        actions["set_voltage"] = mxv
                        actions["set_current"] = mxi
                        self._add_phase_limits(actions, mxv, mxi)
                        actions["notify"] = (
                            "<b>✅ Фаза завершена:</b> Main Charge\n"
                            "<b>🚀 Переход к:</b> Mix Mode (финальный буст)"
                        )
                        actions["log_event"] = "MAIN->MIX"

            elif is_cv and self._detect_stuck_current(current):
                if self._stuck_current_since is None:
                    self._stuck_current_since = now
                stuck_mins = int((now - self._stuck_current_since) / 60)
                if self.antisulfate_count < 3 and stuck_mins >= DESULF_STUCK_MIN_MINUTES:
                    self.antisulfate_count += 1
                    self._stuck_current_since = None
                    self.current_stage = self.STAGE_DESULFATION
                    self.stage_start_time = now
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
                    self.current_stage = self.STAGE_MIX
                    self.stage_start_time = now
                    self.v_max_recorded = voltage
                    self.i_min_recorded = current
                    mxv, mxi = self._mix_target()
                    actions["set_voltage"] = mxv
                    actions["set_current"] = mxi
                    self._add_phase_limits(actions, mxv, mxi)
                    actions["notify"] = (
                        "<b>✅ Переход к:</b> Mix Mode (перемешивание)\n"
                        "Лимит десульфаций достигнут."
                    )
                    actions["log_event"] = "MAIN->MIX (desulf limit)"

            if is_cv and current < (0.3 if self.battery_type != self.PROFILE_AGM else 0.2):
                self._stuck_current_since = None
                if elapsed < 600 and not self._phantom_alerted:
                    self._phantom_alerted = True
                    actions["notify"] = (
                        "<b>⚠️ Мнимый заряд (Phantom Detect)</b>\n"
                        "Bulk < 10 мин. Возможна потеря ёмкости."
                    )
                self.current_stage = self.STAGE_MIX
                self.stage_start_time = now
                self.v_max_recorded = voltage
                self.i_min_recorded = current
                mxv, mxi = self._mix_target()
                actions["set_voltage"] = mxv
                actions["set_current"] = mxi
                self._add_phase_limits(actions, mxv, mxi)
                actions["notify"] = (
                    "<b>✅ Фаза завершена:</b> Main Charge\n"
                    "<b>🚀 Переход к:</b> Mix Mode (перемешивание)"
                )
                actions["log_event"] = "MAIN->MIX"

        # --- ДЕСУЛЬФАТАЦИЯ ---
        elif self.current_stage == self.STAGE_DESULFATION:
            if elapsed >= 2 * 3600:
                self.current_stage = self.STAGE_MAIN
                self.stage_start_time = now
                uv, ui = self._main_target()
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["notify"] = "<b>⏸ Десульфатация завершена.</b> Возврат к Main Charge."
                actions["log_event"] = "DESULFATION->MAIN"

        # --- MIX MODE ---
        elif self.current_stage == self.STAGE_MIX:
            if self.v_max_recorded is None or voltage > self.v_max_recorded:
                self.v_max_recorded = voltage
            if self.i_min_recorded is None or current < self.i_min_recorded:
                self.i_min_recorded = current

            if self._check_delta_finish(voltage, current):
                if not self._delta_reported:
                    self._delta_reported = True
                    self.finish_timer_start = now
                    v_peak = self.v_max_recorded or voltage
                    actions["notify"] = (
                        "<b>📉 Отчёт Delta V:</b>\n"
                        f"Пик {v_peak:.2f}В → спад до {voltage:.2f}В. "
                        "Условие выполнено. Таймер 2ч."
                    )
                if self.finish_timer_start and (now - self.finish_timer_start) >= MIX_DONE_TIMER:
                    self.current_stage = self.STAGE_DONE
                    self.stage_start_time = now
                    uv, ui = self._storage_target()
                    actions["set_voltage"] = uv
                    actions["set_current"] = ui
                    self._add_phase_limits(actions, uv, ui)
                    actions["notify"] = (
                        "<b>✅ Заряд завершён.</b>\n"
                        f"Storage 13.8V/1A. V_max={self.v_max_recorded:.2f}В."
                    )
                    actions["log_event"] = f"DONE ah={ah:.2f}"
                    self._clear_session_file()
            elif self.battery_type == self.PROFILE_EFB and elapsed >= EFB_MIX_MAX_HOURS * 3600:
                self.current_stage = self.STAGE_DONE
                self.stage_start_time = now
                uv, ui = self._storage_target()
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                self._add_phase_limits(actions, uv, ui)
                actions["notify"] = "<b>⏱ EFB Mix:</b> лимит 10ч. Переход в Storage."
                actions["log_event"] = f"DONE ah={ah:.2f} (EFB limit)"
                self._clear_session_file()

        if "notify" in actions:
            self.notify(actions["notify"])

        active = self.current_stage in (
            self.STAGE_PREP,
            self.STAGE_MAIN,
            self.STAGE_DESULFATION,
            self.STAGE_MIX,
        )
        if active and ("notify" in actions or now - self._last_save_time >= 30):
            self._save_session(voltage, current, ah)
            self._last_save_time = now

        return actions
