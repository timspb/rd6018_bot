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

    def build_context(self, hass_data, session_history):
        # hass_data: dict с ключами из sensor/binary_sensor
        # session_history: list из get_last_sessions
        context = []
        context.append(f"Voltage: {hass_data.get('sensor.rd_6018_output_voltage')} V")
        context.append(f"Current: {hass_data.get('sensor.rd_6018_output_current')} A")
        context.append(f"Power: {hass_data.get('sensor.rd_6018_output_power')} W")
        context.append(f"Battery Voltage: {hass_data.get('sensor.rd_6018_battery_voltage')} V")
        context.append(f"Charge: {hass_data.get('sensor.rd_6018_battery_charge')} Ah")
        context.append(f"Energy: {hass_data.get('sensor.rd_6018_battery_energy')} Wh")
        context.append(f"Temp: {hass_data.get('sensor.rd_6018_temperature_external')} C")
        context.append(f"CV Mode: {hass_data.get('binary_sensor.rd_6018_constant_voltage')}")
        context.append(f"CC Mode: {hass_data.get('binary_sensor.rd_6018_constant_current')}")
        context.append(f"Output: {hass_data.get('switch.rd_6018_output')}")
        context.append(f"OVP: {hass_data.get('binary_sensor.rd_6018_over_voltage_protection')}")
        context.append(f"OCP: {hass_data.get('binary_sensor.rd_6018_over_current_protection')}")
        context.append("\nИстория зарядов:")
        for s in session_history:
            context.append(f"{s}")
        return '\n'.join(context)

    def analyze(self, hass_data, session_history):
        # Проверка истории
        if not session_history or len(session_history) < 1:
            return "Мало данных для анализа, подождите 10 минут."
        # Заменяем None на 'N/A' в истории
        session_history_clean = []
        for s in session_history:
            s_clean = tuple("N/A" if v is None else v for v in s)
            session_history_clean.append(s_clean)
        # Определяем режим насыщения
        cv_mode = hass_data.get('binary_sensor.rd_6018_constant_voltage') == 'on'
        # Жестко прописываем model и max_tokens
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "Анализируй заряд АКБ RD6018. Если ток в режиме CV не падает — предупреди о КЗ. Учитывай историю деградации."},
                {"role": "user", "content": self.build_context(hass_data, session_history_clean)}
            ],
            "max_tokens": 1024
        }
        # Убедимся, что max_tokens — integer
        if isinstance(payload["max_tokens"], str):
            payload["max_tokens"] = int(payload["max_tokens"])
        print(f"DEBUG PAYLOAD: {payload}")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        # Проверяем роли в ответе
        choices = response.json()["choices"]
        for c in choices:
            if c["message"]["role"] not in ["system", "user", "assistant"]:
                return "Ошибка: некорректная роль в ответе AI."
        return choices[0]["message"]["content"]
