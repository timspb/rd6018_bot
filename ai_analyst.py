import os
import requests
import sqlite3
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

class AIAnalyst:
    def __init__(self, db_path='rd6018_charge.db'):
        self.db_path = db_path
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL

    def get_last_sessions(self, limit=10):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''SELECT id, start_time, battery_type, state, v_max_mix, i_min_mix, ah_total FROM current_session ORDER BY id DESC LIMIT ?''', (limit,))
        sessions = cursor.fetchall()
        conn.close()
        return sessions

    def analyze(self, current_logs, summary=None):
        payload = {
            "messages": [
                {"role": "system", "content": "Analyze battery charge session. Detect CV anomalies, short-circuit risk, and degradation."},
                {"role": "user", "content": f"Current logs: {current_logs}\nSummary: {summary}"}
            ]
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        response = requests.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
