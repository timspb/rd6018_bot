"""
config.py — конфигурация RD6018 Async Bot.
Все токены и URL берутся из .env.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram (поддержка TG_TOKEN и TELEGRAM_BOT_TOKEN)
TG_TOKEN = (os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()

# Home Assistant
HA_URL = (os.getenv("HA_URL") or "").rstrip("/")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# v2.6 Часовой пояс для всех временных меток
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Europe/Moscow")

# Разрешённые chat_id (через запятую). Пусто = доступ у всех.
def _parse_allowed_chat_ids() -> tuple:
    raw = (os.getenv("ALLOWED_CHAT_IDS") or "").strip()
    if not raw:
        return ()
    result = []
    for s in raw.split(","):
        s = s.strip()
        if not s:
            continue
        try:
            result.append(int(s))
        except ValueError:
            pass
    return tuple(result)


ALLOWED_CHAT_IDS = _parse_allowed_chat_ids()

# Строгий маппинг сущностей HA (как в спецификации)
ENTITY_MAP = {
    "voltage": "sensor.rd_6018_output_voltage",
    "battery_voltage": "sensor.rd_6018_battery_voltage",
    "current": "sensor.rd_6018_output_current",
    "power": "sensor.rd_6018_output_power",
    "ah": "sensor.rd_6018_battery_charge",
    "wh": "sensor.rd_6018_battery_energy",
    # v2.0: Разделение датчиков — внутренняя температура БП и внешняя АКБ (K-тип). Защита 45°C только по temp_ext.
    "temp_int": "sensor.rd_6018_temperature",           # внутренняя температура блока питания
    "temp_ext": "sensor.rd_6018_temperature_external",  # внешний датчик на АКБ (K-тип), используется для 35/40/45°C
    "is_cv": "binary_sensor.rd_6018_constant_voltage",
    "is_cc": "binary_sensor.rd_6018_constant_current",
    "switch": "switch.rd_6018_output",
    "set_voltage": "number.rd_6018_output_voltage",
    "set_current": "number.rd_6018_output_current",
    "ovp": "number.rd_6018_over_voltage_protection",
    "ocp": "number.rd_6018_over_current_protection",
    "input_voltage": "sensor.rd_6018_input_voltage",  # Может отсутствовать в некоторых интеграциях
    "uptime": "sensor.rd_6018_uptime",  # Может отсутствовать в некоторых интеграциях
}

# Лимиты безопасности
MAX_VOLTAGE = 16.6  # V — предупреждение
# Температура: 34°C (предупреждение), 37°C (авария) — в charge_logic.py
