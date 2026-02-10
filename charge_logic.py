"""
charge_logic.py — State Machine заряда для Ca/Ca, EFB, AGM.
"""
import logging
import time
from collections import deque
from typing import Any, Callable, Dict, Optional, Tuple

from config import ENTITY_MAP, MAX_TEMP, MAX_TEMP_AGM, MAX_VOLTAGE

logger = logging.getLogger("rd6018")


class ChargeController:
    """
    Контроллер заряда с машиной состояний.
    Этапы: SoftStart, Bulk, Desulfation, Mix, Done.
    """

    STAGE_SOFT_START = "SoftStart"
    STAGE_BULK = "Bulk"
    STAGE_DESULFATION = "Desulfation"
    STAGE_MIX = "Mix"
    STAGE_DONE = "Done"
    STAGE_IDLE = "Idle"

    STAGE_TIMEOUTS = {"Ca/Ca": 8 * 3600, "EFB": 10 * 3600, "AGM": 5 * 3600}

    def __init__(self, hass_client: Any, notify_cb: Optional[Callable[[str], Any]] = None) -> None:
        self.hass = hass_client
        self.notify = notify_cb or (lambda _: None)
        self.battery_type: str = "Ca/Ca"
        self.ah_capacity: int = 60
        self.current_stage: str = self.STAGE_IDLE
        self.stage_start_time: float = 0.0
        self.antisulfate_count: int = 0
        self.v_max_recorded: Optional[float] = None
        self.i_min_recorded: Optional[float] = None
        self.plateau_currents: deque = deque(maxlen=4)  # каждые 10 мин, 40 мин
        self.finish_timer_start: Optional[float] = None
        self.bulk_start_time: Optional[float] = None
        self.is_cv: bool = False
        self._last_plateau_save: float = 0.0
        self._phantom_alerted: bool = False

    def start(self, battery_type: str, ah_capacity: int) -> None:
        """Запуск заряда по профилю."""
        self.battery_type = battery_type
        self.ah_capacity = ah_capacity
        self.current_stage = self.STAGE_SOFT_START
        self.stage_start_time = time.time()
        self.antisulfate_count = 0
        self.v_max_recorded = None
        self.i_min_recorded = None
        self.plateau_currents.clear()
        self.finish_timer_start = None
        self.bulk_start_time = None
        self._phantom_alerted = False
        logger.info("ChargeController started: %s %dAh", battery_type, ah_capacity)

    def stop(self) -> None:
        """Остановка."""
        self.current_stage = self.STAGE_IDLE

    @property
    def stage_timeout_sec(self) -> float:
        return float(self.STAGE_TIMEOUTS.get(self.battery_type, 8 * 3600))

    def _soft_start_target(self) -> Tuple[float, float]:
        return (12.0, 0.5)

    def _bulk_target(self) -> Tuple[float, float]:
        if self.battery_type == "Ca/Ca":
            return (14.7, 0.5 * self.ah_capacity)
        if self.battery_type == "EFB":
            return (14.8, 0.5 * self.ah_capacity)
        if self.battery_type == "AGM":
            return (14.4, 0.5 * self.ah_capacity)
        return (14.4, 0.5 * self.ah_capacity)

    def _mix_target(self) -> Tuple[float, float]:
        pct = 0.03 * self.ah_capacity
        if self.battery_type == "Ca/Ca":
            return (16.5, max(0.1, pct))
        if self.battery_type == "EFB":
            return (16.5, max(0.1, pct))
        if self.battery_type == "AGM":
            return (16.3, max(0.1, 0.02 * self.ah_capacity))
        return (16.3, max(0.1, pct))

    def _storage_target(self) -> Tuple[float, float]:
        return (13.8, 1.0)

    def detect_plateau(self, current_i: float, target_i: float) -> bool:
        """
        Детектор полки: каждые 10 мин сохранять ток.
        Если 40 мин ток не снижается > 0.01A и > целевого — стагнация.
        """
        now = time.time()
        if now - self._last_plateau_save < 600:  # 10 мин
            return False
        self._last_plateau_save = now
        self.plateau_currents.append(current_i)
        if len(self.plateau_currents) < 4:
            return False
        vals = list(self.plateau_currents)
        if max(vals) - min(vals) <= 0.01 and current_i > target_i:
            logger.info("Plateau detected: I=%.3f stable 40min > target %.3f", current_i, target_i)
            return True
        return False

    def check_delta_finish(self, v_now: float, i_now: float) -> bool:
        """
        На этапе Mix: если V падает на 0.03V от пика или I растёт на 0.03A от мин — триггер.
        """
        if self.v_max_recorded is None or self.i_min_recorded is None:
            return False
        if v_now <= self.v_max_recorded - 0.03:
            logger.info("Delta V: V_max=%.3f, now=%.3f, delta=0.03V", self.v_max_recorded, v_now)
            return True
        if i_now >= self.i_min_recorded + 0.03:
            logger.info("Delta I: I_min=%.3f, now=%.3f, delta=0.03A", self.i_min_recorded, i_now)
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
        Основной цикл. Вызывается из фоновой задачи.
        Возвращает dict с действиями: set_voltage, set_current, turn_off, notify, etc.
        """
        actions: Dict[str, Any] = {}

        if temp_ext is not None:
            limit = MAX_TEMP_AGM if self.battery_type == "AGM" else MAX_TEMP
            if temp_ext > limit:
                actions["emergency_stop"] = True
                actions["notify"] = (
                    f"🚨 КРИТИЧЕСКИЙ ПЕРЕГРЕВ! T={temp_ext:.1f}°C. Питание отключено."
                )
                return actions

        if voltage > MAX_VOLTAGE:
            actions["notify"] = f"⚠️ Напряжение {voltage:.2f}V превышает лимит!"

        self.is_cv = is_cv

        if self.current_stage == self.STAGE_IDLE:
            return actions

        elapsed = time.time() - self.stage_start_time
        if elapsed > self.stage_timeout_sec:
            actions["emergency_stop"] = True
            actions["notify"] = f"⏱ Таймаут этапа {self.current_stage} ({self.stage_timeout_sec/3600:.0f}ч). Аварийный стоп."
            return actions

        # SoftStart
        if self.current_stage == self.STAGE_SOFT_START:
            uv, ui = self._soft_start_target()
            if voltage < 12.0:
                actions["set_voltage"] = uv
                actions["set_current"] = ui
            else:
                self.current_stage = self.STAGE_BULK
                self.stage_start_time = time.time()
                self.bulk_start_time = time.time()
                uv, ui = self._bulk_target()
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                actions["notify"] = "✅ SoftStart завершён. Начинаю Bulk."

        # Bulk
        elif self.current_stage == self.STAGE_BULK:
            uv, ui = self._bulk_target()
            target_i_cv = 0.3 if self.battery_type != "AGM" else 0.2
            if is_cv and current < target_i_cv:
                bulk_duration = time.time() - (self.bulk_start_time or time.time())
                if bulk_duration < 600 and not self._phantom_alerted:
                    self._phantom_alerted = True
                    actions["notify"] = "⚠️ Мнимый заряд! Bulk < 10 мин. Потеря ёмкости?"
                self.current_stage = self.STAGE_MIX
                self.stage_start_time = time.time()
                self.v_max_recorded = voltage
                self.i_min_recorded = current
                mxv, mxi = self._mix_target()
                actions["set_voltage"] = mxv
                actions["set_current"] = mxi
                actions["notify"] = "✅ Bulk завершён. Начинаю Mix."
            elif is_cv and self.detect_plateau(current, target_i_cv):
                if self.antisulfate_count < (4 if self.battery_type == "AGM" else 3):
                    self.antisulfate_count += 1
                    self.current_stage = self.STAGE_DESULFATION
                    self.stage_start_time = time.time()
                    ds_v = 16.3 if self.battery_type == "AGM" else 16.3
                    ds_i = max(0.1, 0.02 * self.ah_capacity)
                    actions["set_voltage"] = ds_v
                    actions["set_current"] = ds_i
                    actions["notify"] = f"🔧 Антисульфат #{self.antisulfate_count}. 16.3V / 2% Ah на 2ч."
                else:
                    actions["notify"] = "❌ Батарея не принимает заряд. Проверьте состояние."

        # Desulfation
        elif self.current_stage == self.STAGE_DESULFATION:
            if elapsed > 2 * 3600:
                self.current_stage = self.STAGE_BULK
                self.stage_start_time = time.time()
                uv, ui = self._bulk_target()
                actions["set_voltage"] = uv
                actions["set_current"] = ui
                actions["notify"] = "⏸ Пауза 30 мин (имитация). Возврат к Bulk."

        # Mix
        elif self.current_stage == self.STAGE_MIX:
            if self.v_max_recorded is None or voltage > self.v_max_recorded:
                self.v_max_recorded = voltage
            if self.i_min_recorded is None or current < self.i_min_recorded:
                self.i_min_recorded = current

            if self.check_delta_finish(voltage, current):
                if self.finish_timer_start is None:
                    self.finish_timer_start = time.time()
                    actions["notify"] = (
                        f"📉 Mix: V_max={self.v_max_recorded:.2f}V, текущее V={voltage:.2f}V. "
                        "Дельта 0.03В достигнута. Таймер 2ч."
                    )
            if self.finish_timer_start is not None:
                if time.time() - self.finish_timer_start >= 2 * 3600:
                    self.current_stage = self.STAGE_DONE
                    self.stage_start_time = time.time()
                    uv, ui = self._storage_target()
                    actions["set_voltage"] = uv
                    actions["set_current"] = ui
                    actions["notify"] = (
                        f"✅ Заряд завершён. Storage 13.8V/1A. "
                        f"V_max было {self.v_max_recorded:.2f}V, закончили на {voltage:.2f}V."
                    )

        return actions
