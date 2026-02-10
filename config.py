# config.py
# Конфигурация железа и константы

HA_URL = 'http://your-home-assistant.local:8123'  # URL Home Assistant
HA_TOKEN = 'your-long-lived-access-token'         # Long-Lived Access Token

ENTITY_IDS = {
    'voltage_set': 'number.rd_6018_output_voltage',
    'current_set': 'number.rd_6018_output_current',
    'output_switch': 'switch.rd_6018_output',
    'voltage_sensor': 'sensor.rd_6018_output_voltage',
    'current_sensor': 'sensor.rd_6018_output_current',
    'temp_sensor': 'sensor.rd_6018_temperature_external',
    'cv_mode': 'binary_sensor.rd_6018_constant_voltage',
}

# Пороги безопасности
MAX_TEMP = 45.0
MAX_VOLTAGE = 17.0

# Токен Telegram-бота
TOKEN = 'your-telegram-bot-token'
