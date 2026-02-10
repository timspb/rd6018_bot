
# config.py — только переменные и лимиты, все токены и URL берутся из .env
import os
from dotenv import load_dotenv
load_dotenv()

# Home Assistant
HA_URL = os.getenv('HA_URL')
HA_TOKEN = os.getenv('HA_TOKEN')

# DeepSeek
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL')

# RD6018 Entity IDs (только актуальные)
ENTITY_IDS = {
    # Sensors
    'output_voltage': 'sensor.rd_6018_output_voltage',
    'output_current': 'sensor.rd_6018_output_current',
    'output_power': 'sensor.rd_6018_output_power',
    'battery_voltage': 'sensor.rd_6018_battery_voltage',
    'battery_charge': 'sensor.rd_6018_battery_charge',
    'battery_energy': 'sensor.rd_6018_battery_energy',
    'temperature': 'sensor.rd_6018_temperature',
    'temperature_external': 'sensor.rd_6018_temperature_external',
    'uptime': 'sensor.rd_6018_uptime',
    # Numbers
    'set_voltage': 'number.rd_6018_output_voltage',
    'set_current': 'number.rd_6018_output_current',
    'ovp': 'number.rd_6018_over_voltage_protection',
    'ocp': 'number.rd_6018_over_current_protection',
    'backlight': 'number.rd_6018_backlight',
    # Switches
    'output_switch': 'switch.rd_6018_output',
    # Binary Sensors
    'cv_mode': 'binary_sensor.rd_6018_constant_voltage',
    'cc_mode': 'binary_sensor.rd_6018_constant_current',
    'battery_mode': 'binary_sensor.rd_6018_battery_mode',
    'keypad_lock': 'binary_sensor.rd_6018_keypad_lock',
    'ovp_tripped': 'binary_sensor.rd_6018_over_voltage_protection',
    'ocp_tripped': 'binary_sensor.rd_6018_over_current_protection',
}

# Safety limits
MAX_TEMP = 45.0  # °C
MAX_VOLTAGE = 17.0  # V

