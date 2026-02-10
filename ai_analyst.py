import os
import requests
import sqlite3
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

class AIAnalyst:
    def __init__(self, db_path='rd6018_charge.db'):
        self.db_path = db_path
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL

    def get_last_sessions(self, user_id=None, device_id=None, limit=10):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query = 'SELECT id, start_time, battery_type, state, v_max_mix, i_min_mix, ah_total FROM current_session'
        params = []
        if user_id:
            query += ' WHERE user_id=?'
            params.append(user_id)
        query += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        cursor.execute(query, tuple(params))
        sessions = cursor.fetchall()
        conn.close()
        return sessions

    def build_context(self, hass_data, session_history, ah_now=None, charge_time_min=None):
        context = []
        context.append(f"Voltage: {hass_data.get('sensor.rd_6018_output_voltage')} V")
        context.append(f"Current: {hass_data.get('sensor.rd_6018_output_current')} A")
        context.append(f"Power: {hass_data.get('sensor.rd_6018_output_power')} W")
        context.append(f"Temp: {hass_data.get('sensor.rd_6018_temperature_external')} C")
        if ah_now is not None:
            context.append(f"Current Ah: {ah_now}")
        if charge_time_min is not None:
            context.append(f"Charge Time: {charge_time_min} min")
        context.append("\nИстория зарядов:")
        for s in session_history:
            context.append(f"{s}")
        return '\n'.join(context)

    def analyze(self, hass_data, session_history):
        if not session_history or len(session_history) < 1:
            return "Мало данных для анализа, подождите 10 минут."
        session_history_clean = []
        for s in session_history:
            s_clean = tuple("N/A" if v is None else v for v in s)
            session_history_clean.append(s_clean)
        # Получаем текущую емкость и время заряда
        ah_now = hass_data.get('sensor.rd_6018_battery_charge')
        # Время с начала заряда (минуты)
        # Для примера: если есть start_time в session_history[0][1]
        charge_time_min = None
        try:
            from datetime import datetime
            start_time = session_history[0][1]
            if start_time and isinstance(start_time, str):
                dt_start = datetime.fromisoformat(start_time)
                charge_time_min = int((datetime.now() - dt_start).total_seconds() // 60)
        except Exception:
            pass
        # Новый системный промпт
        sys_prompt = (
            "Ты эксперт по зарядке АКБ RD6018. "
            "Анализируй заряд, учитывай деградацию и историю. "
            f"Текущая емкость: {ah_now} Ah. Время с начала заряда: {charge_time_min} мин. "
            "Главный вопрос: Сколько времени осталось до 100%? Прогнозируй по падению тока. "
            "Если ток в режиме CV не падает — предупреди о КЗ."
        )
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": self.build_context(hass_data, session_history_clean, ah_now, charge_time_min)}
            ],
            "max_tokens": 1024
        }
        if isinstance(payload["max_tokens"], str):
            payload["max_tokens"] = int(payload["max_tokens"])
        print(f"DEBUG PAYLOAD: {payload}")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        choices = response.json()["choices"]
        for c in choices:
            if c["message"]["role"] not in ["system", "user", "assistant"]:
                return "Ошибка: некорректная роль в ответе AI."
        return choices[0]["message"]["content"]
