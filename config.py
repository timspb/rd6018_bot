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

# Маппинг сущностей HA (RD6018).
# Legacy сущности оставлены для бесшовной миграции. Публичные сущности из
# esphome/packages/rd6018_telemetry_v2.yaml создаются production HA под
# device-prefixed namespace ``rd6018_rd_6018_*``. Для safety/diagnostic V2
# каналов используем точные deterministic IDs этого namespace, без fuzzy search.
ENTITY_MAP = {
    "voltage": "sensor.rd_6018_output_voltage",
    "battery_voltage": "sensor.rd_6018_battery_voltage",
    "current": "sensor.rd_6018_output_current",
    "power": "sensor.rd_6018_output_power",
    "power_v2": "sensor.rd6018_rd_6018_output_power_v2",
    "ah": "sensor.rd_6018_battery_charge",
    "wh": "sensor.rd_6018_battery_energy",
    "temp_int": "sensor.rd_6018_temperature",
    "temp_ext": "sensor.rd_6018_temperature_external",
    "temp_int_v2": "sensor.rd6018_rd_6018_temperature_internal_v2",
    "temp_ext_v2": "sensor.rd6018_rd_6018_temperature_external_v2",
    "is_cv": "binary_sensor.rd_6018_constant_voltage",
    "is_cc": "binary_sensor.rd_6018_constant_current",
    "regulation_code": "sensor.rd6018_rd_6018_regulation_mode_code",
    "protection_code": "sensor.rd6018_rd_6018_protection_status_code",
    # Force-updated read-only register-18 mirror. The public switch remains the
    # actuator endpoint; this sensor owns canonical Output freshness in V2.
    "output_state_code_v2": "sensor.rd6018_rd_6018_output_state_code_v2",
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
    # This is ESPHome bridge uptime, not RD6018 controller uptime.
    "uptime": "sensor.rd_6018_uptime",
    "model_number": "sensor.rd6018_rd_6018_model_number_v2",
    "serial_number": "sensor.rd6018_rd_6018_serial_number_v2",
    "firmware_version": "sensor.rd6018_rd_6018_firmware_version_v2",
    "active_preset": "sensor.rd6018_rd_6018_active_preset_v2",
    "take_ok": "binary_sensor.rd6018_rd_6018_take_ok_v2",
    "take_out": "binary_sensor.rd6018_rd_6018_take_out_v2",
    "boot_power": "binary_sensor.rd6018_rd_6018_boot_power_v2",
    # Calibration entities are disabled_by_default in ESPHome, so HA may not
    # expose them until explicitly enabled. Their deterministic IDs are still
    # pinned here so enabling them cannot resurrect the legacy wrong namespace.
    "cal_vout_zero": "sensor.rd6018_rd_6018_cal_vout_zero",
    "cal_vout_scale": "sensor.rd6018_rd_6018_cal_vout_scale",
    "cal_vbat_zero": "sensor.rd6018_rd_6018_cal_vbat_zero",
    "cal_vbat_scale": "sensor.rd6018_rd_6018_cal_vbat_scale",
    "cal_iout_zero": "sensor.rd6018_rd_6018_cal_iout_zero",
    "cal_iout_scale": "sensor.rd6018_rd_6018_cal_iout_scale",
    "cal_ibat_zero": "sensor.rd6018_rd_6018_cal_ibat_zero",
    "cal_ibat_scale": "sensor.rd6018_rd_6018_cal_ibat_scale",
}

# Лимиты безопасности
MAX_VOLTAGE = 16.6  # V — legacy profile ceiling; expert/manual V2 has its own ceiling
MAX_MANUAL_VOLTAGE = 17.5  # V — user command above this value is never accepted
MIN_INPUT_VOLTAGE = 60.0  # V — PSU health reference only; not battery/FSM authority in V2
TEMP_INT_PRECRITICAL = 55.0  # °C — выключение выхода при температуре блока (защита БП)
# Температура АКБ: фактические уровни 35/40/45°C определены в charge_logic.py
