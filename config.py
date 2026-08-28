"""
config.py — конфигурация RD6018 Async Bot.
Все токены и URL берутся из .env.
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}

# Telegram (поддержка TG_TOKEN и TELEGRAM_BOT_TOKEN)
TG_TOKEN = (os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()

# Home Assistant
HA_URL = (os.getenv("HA_URL") or "").rstrip("/")
HA_LOCAL_URL = (os.getenv("HA_LOCAL_URL") or "https://192.168.1.102:8123").rstrip("/")
HA_PREFER_LOCAL = _as_bool(os.getenv("HA_PREFER_LOCAL"), default=True)
HA_INSECURE_LOCAL = _as_bool(os.getenv("HA_INSECURE_LOCAL"), default=True)

if HA_PREFER_LOCAL and ("rd.timspb.ru" in HA_URL or not HA_URL):
    HA_URL = HA_LOCAL_URL

HA_TOKEN = os.getenv("HA_TOKEN", "")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# v2.6 Часовой пояс для всех временных меток
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Europe/Moscow")

# Разрешённые chat_id (через запятую).
# По умолчанию управление физическим выходом fail-closed: пустой whitelist
# не означает «доступ всем». Для намеренно публичного/тестового бота требуется
# явный ALLOW_ALL_CHATS=1.
ALLOW_ALL_CHATS = _as_bool(os.getenv("ALLOW_ALL_CHATS"), default=False)


def _parse_allowed_chat_ids() -> tuple:
    raw = (os.getenv("ALLOWED_CHAT_IDS") or "").strip()
    if not raw:
        # bot._is_chat_allowed() исторически трактует пустой tuple как allow-all.
        # Поэтому используем невозможный Telegram chat_id sentinel, пока UI слой
        # не будет переведён на явный policy object.
        return () if ALLOW_ALL_CHATS else (-1,)
    result = []
    for s in raw.split(","):
        s = s.strip()
        if not s:
            continue
        try:
            result.append(int(s))
        except ValueError:
            pass
    if result:
        return tuple(result)
    return () if ALLOW_ALL_CHATS else (-1,)


ALLOWED_CHAT_IDS = _parse_allowed_chat_ids()

# Маппинг сущностей HA (RD6018)
ENTITY_MAP = {
    "voltage": "sensor.rd_6018_output_voltage",
    "battery_voltage": "sensor.rd_6018_battery_voltage",
    "current": "sensor.rd_6018_output_current",
    "power": "sensor.rd_6018_output_power",
    "ah": "sensor.rd_6018_battery_charge",
    "wh": "sensor.rd_6018_battery_energy",
    "temp_int": "sensor.rd_6018_temperature",
    "temp_ext": "sensor.rd_6018_temperature_external",
    "is_cv": "binary_sensor.rd_6018_constant_voltage",
    "is_cc": "binary_sensor.rd_6018_constant_current",
    "battery_mode": "binary_sensor.rd_6018_battery_mode",
    "keypad_lock": "binary_sensor.rd_6018_keypad_lock",
    "ovp_triggered": "binary_sensor.rd_6018_over_voltage_protection",
    "ocp_triggered": "binary_sensor.rd_6018_over_current_protection",
    "switch": "switch.rd_6018_output",
    "set_voltage": "number.rd_6018_output_voltage",
    "set_current": "number.rd_6018_output_current",
    "ovp": "number.rd_6018_over_voltage_protection",
    "ocp": "number.rd_6018_over_current_protection",
    "backlight": "number.rd_6018_backlight",
    "input_voltage": "sensor.rd_6018_input_voltage",
    "uptime": "sensor.rd_6018_uptime",
}

# Лимиты безопасности
MAX_VOLTAGE = 16.6  # V — legacy profile ceiling; expert V2 recipes have their own explicit ceiling
MIN_INPUT_VOLTAGE = 60.0  # В — не включать заряд при входном напряжении ниже
TEMP_INT_PRECRITICAL = 55.0  # °C — выключение выхода при температуре блока (защита БП)
# Температура АКБ: фактические уровни 35/40/45°C определены в charge_logic.py
