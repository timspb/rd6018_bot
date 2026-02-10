import asyncio
import time
from collections import deque
from statistics import median
from database import Database
from hass_api import HassAPI
from config import ENTITY_IDS, MAX_TEMP

class ChargeController:
    def __init__(self, hass_api: HassAPI, db: Database, session_id: int):
        self.hass = hass_api
        self.db = db
        self.session_id = session_id
        self.current_state = 'IDLE'
        self.current_stage_start = time.time()
        self.antisulfate_count = 0
        self.v_max_mix = None
        self.i_min_mix = None
        self.plateau_history = deque(maxlen=40*60)  # 40 минут, 1 запись в сек
        self.bulk_start_time = None
        self.bulk_end_time = None
        self.finish_timer = None
        self.plateau_detected = False
        self.mim_charge_flag = False
        logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

    async def update_plateau_history(self, current_i):
        self.plateau_history.append(current_i)
        # Медианное фильтрование для защиты от шумов
        if len(self.plateau_history) >= 60:
            minute_values = list(self.plateau_history)[-60:]
            avg_i = sum(minute_values) / len(minute_values)
            self.plateau_history[-1] = avg_i
        logging.info(f'Ток обновлен: {current_i}')

    def detect_plateau(self):
        if len(self.plateau_history) < 40*60:
            return False
        max_i = max(self.plateau_history)
        min_i = min(self.plateau_history)
        if max_i - min_i < 0.02:
            self.plateau_detected = True
            logging.info('Полка обнаружена')
            return True
        return False

    def detect_mim_charge(self):
        if self.bulk_start_time and self.bulk_end_time:
            duration = self.bulk_end_time - self.bulk_start_time
            if duration < 15*60:
                self.mim_charge_flag = True
                self.db.log(self.session_id, '⚠️ Мнимый заряд!')
                self.db.update_session(self.session_id, mim_charge=1)

    def mix_logic(self, current_v, current_i):
        elapsed = time.time() - self.current_stage_start
        # Начинаем поиск пика напряжения и минимума тока только через 30 минут
        if elapsed >= 30 * 60:
            if self.v_max_mix is None or current_v > self.v_max_mix:
                self.v_max_mix = current_v
                logging.info(f'Mix: Новый V_max = {self.v_max_mix}')
            if self.i_min_mix is None or current_i < self.i_min_mix:
                self.i_min_mix = current_i
                logging.info(f'Mix: Новый I_min = {self.i_min_mix}')
            # Delta V/I — только после 30 минут
            if current_v <= self.v_max_mix - 0.03:
                if not self.finish_timer:
                    self.finish_timer = time.time()
                    self.db.log(self.session_id, 'Mix: V упало на 0.03В от пика — запуск финального таймера 2ч')
                    logging.info('Mix: V упало на 0.03В от пика — старт таймера')
            if current_i >= self.i_min_mix + 0.03:
                if not self.finish_timer:
                    self.finish_timer = time.time()
                    self.db.log(self.session_id, 'Mix: I вырос на 0.03А от минимума — запуск финального таймера 2ч')
                    logging.info('Mix: I вырос на 0.03А от минимума — старт таймера')
        else:
            # До 30 минут просто фиксируем пики
            if self.v_max_mix is None or current_v > self.v_max_mix:
                self.v_max_mix = current_v
                logging.info(f'Mix: Новый V_max (до 30 мин) = {self.v_max_mix}')
            if self.i_min_mix is None or current_i < self.i_min_mix:
                self.i_min_mix = current_i
                logging.info(f'Mix: Новый I_min (до 30 мин) = {self.i_min_mix}')
                self.db.log(self.session_id, 'Mix: Delta V/I — запуск финального таймера 2ч')

    async def safety_check(self):
        temp, _ = await self.hass.get_state(ENTITY_IDS['temp_sensor'])
        if float(temp) > MAX_TEMP:
            await self.hass.turn_off_switch(ENTITY_IDS['output_switch'])
            self.db.log(self.session_id, f'Температура {temp}°C — выключение выхода!')

    # ...дополнительная логика переходов и управления...
