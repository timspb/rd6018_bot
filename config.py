"""
config.py вЂ” РєРѕРЅС„РёРіСѓСЂР°С†РёСЏ RD6018 Async Bot.
Р’СЃРµ С‚РѕРєРµРЅС‹ Рё URL Р±РµСЂСѓС‚СЃСЏ РёР· .env.
"""
import os
from typing import Optional
from dotenv import load_dotenv
from runtime.safety.voltage_variables import PB_AUTOMATIC_TARGET_CEILING_V

load_dotenv()


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}

# Telegram (РїРѕРґРґРµСЂР¶РєР° TG_TOKEN Рё TELEGRAM_BOT_TOKEN)
TG_TOKEN = (os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()

# Home Assistant
HA_URL = (os.getenv("HA_URL") or "").rstrip("/")
HA_LOCAL_URL = (os.getenv("HA_LOCAL_URL") or "").rstrip("/")
HA_PREFER_LOCAL = _as_bool(os.getenv("HA_PREFER_LOCAL"), default=False)
HA_INSECURE_LOCAL = _as_bool(os.getenv("HA_INSECURE_LOCAL"), default=True)

if HA_PREFER_LOCAL and HA_LOCAL_URL and ("rd.timspb.ru" in HA_URL or not HA_URL):
    HA_URL = HA_LOCAL_URL

HA_TOKEN = os.getenv("HA_TOKEN", "")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# v2.6 Р§Р°СЃРѕРІРѕР№ РїРѕСЏСЃ РґР»СЏ РІСЃРµС… РІСЂРµРјРµРЅРЅС‹С… РјРµС‚РѕРє
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Europe/Moscow")

# Р Р°Р·СЂРµС€С‘РЅРЅС‹Рµ chat_id (С‡РµСЂРµР· Р·Р°РїСЏС‚СѓСЋ).
# РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ СѓРїСЂР°РІР»РµРЅРёРµ С„РёР·РёС‡РµСЃРєРёРј РІС‹С…РѕРґРѕРј fail-closed: РїСѓСЃС‚РѕР№ whitelist
# РЅРµ РѕР·РЅР°С‡Р°РµС‚ В«РґРѕСЃС‚СѓРї РІСЃРµРјВ». Р”Р»СЏ РЅР°РјРµСЂРµРЅРЅРѕ РїСѓР±Р»РёС‡РЅРѕРіРѕ/С‚РµСЃС‚РѕРІРѕРіРѕ Р±РѕС‚Р° С‚СЂРµР±СѓРµС‚СЃСЏ
# СЏРІРЅС‹Р№ ALLOW_ALL_CHATS=1.
ALLOW_ALL_CHATS = _as_bool(os.getenv("ALLOW_ALL_CHATS"), default=False)


def _parse_allowed_chat_ids() -> tuple:
    raw = (os.getenv("ALLOWED_CHAT_IDS") or "").strip()
    if not raw:
        # bot._is_chat_allowed() РёСЃС‚РѕСЂРёС‡РµСЃРєРё С‚СЂР°РєС‚СѓРµС‚ РїСѓСЃС‚РѕР№ tuple РєР°Рє allow-all.
        # РџРѕСЌС‚РѕРјСѓ РёСЃРїРѕР»СЊР·СѓРµРј РЅРµРІРѕР·РјРѕР¶РЅС‹Р№ Telegram chat_id sentinel, РїРѕРєР° UI СЃР»РѕР№
        # РЅРµ Р±СѓРґРµС‚ РїРµСЂРµРІРµРґС‘РЅ РЅР° СЏРІРЅС‹Р№ policy object.
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

# РњР°РїРїРёРЅРі СЃСѓС‰РЅРѕСЃС‚РµР№ HA (RD6018).
# Legacy СЃСѓС‰РЅРѕСЃС‚Рё РѕСЃС‚Р°РІР»РµРЅС‹ РґР»СЏ Р±РµСЃС€РѕРІРЅРѕР№ РјРёРіСЂР°С†РёРё. РџСѓР±Р»РёС‡РЅС‹Рµ СЃСѓС‰РЅРѕСЃС‚Рё РёР·
# esphome/packages/rd6018_telemetry_v2.yaml СЃРѕР·РґР°СЋС‚СЃСЏ production HA РїРѕРґ
# device-prefixed namespace ``rd6018_rd_6018_*``. Р”Р»СЏ safety/diagnostic V2
# РєР°РЅР°Р»РѕРІ РёСЃРїРѕР»СЊР·СѓРµРј С‚РѕС‡РЅС‹Рµ deterministic IDs СЌС‚РѕРіРѕ namespace, Р±РµР· fuzzy search.
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
    # Writable number entities remain the actuator endpoints. Safety readback is
    # intentionally separate: a same-value number write may not advance HA metadata.
    "set_voltage": "number.rd_6018_output_voltage",
    "set_current": "number.rd_6018_output_current",
    "ovp": "number.rd_6018_over_voltage_protection",
    "ocp": "number.rd_6018_over_current_protection",
    "set_voltage_readback_v2": "sensor.rd6018_rd_6018_set_voltage_readback_v2",
    "set_current_readback_v2": "sensor.rd6018_rd_6018_set_current_readback_v2",
    "ovp_readback_v2": "sensor.rd6018_rd_6018_ovp_readback_v2",
    "ocp_readback_v2": "sensor.rd6018_rd_6018_ocp_readback_v2",
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
    # Read-only edge authority; the bot never infers or writes this state.
    "autonomous_mode": "binary_sensor.rd6018_rd_6018_safety_autonomous_mode",
    "safety_modbus_age": "sensor.rd6018_rd_6018_safety_modbus_age",
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

# Р›РёРјРёС‚С‹ Р±РµР·РѕРїР°СЃРЅРѕСЃС‚Рё
MAX_VOLTAGE = float(PB_AUTOMATIC_TARGET_CEILING_V.default)  # compatibility alias; canonical owner: runtime.safety.voltage
MAX_MANUAL_VOLTAGE = 17.5  # V вЂ” user command above this value is never accepted
MIN_INPUT_VOLTAGE = 60.0  # V вЂ” PSU health reference only; not battery/FSM authority in V2
TEMP_INT_PRECRITICAL = 55.0  # В°C вЂ” РІС‹РєР»СЋС‡РµРЅРёРµ РІС‹С…РѕРґР° РїСЂРё С‚РµРјРїРµСЂР°С‚СѓСЂРµ Р±Р»РѕРєР° (Р·Р°С‰РёС‚Р° Р‘Рџ)
# Battery temperature thresholds are owned by modular safety/strategy policy.
