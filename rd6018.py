from hass_api import HassAPI
from config import HA_URL, HA_TOKEN, ENTITY_IDS

class RD6018:
    def __init__(self):
        self.hass = HassAPI(HA_URL, HA_TOKEN)

    async def get_current_metrics(self):
        for _ in range(3):
            try:
                voltage, _ = await self.hass.get_state(ENTITY_IDS['voltage_sensor'])
                current, _ = await self.hass.get_state(ENTITY_IDS['current_sensor'])
                temp, _ = await self.hass.get_state(ENTITY_IDS['temp_sensor'])
                cv_flag, _ = await self.hass.get_state(ENTITY_IDS['cv_mode'])
                # Если что-то не получено — повтор
                if None in (voltage, current, temp, cv_flag):
                    raise Exception('Не удалось получить данные от HA')
                return {
                    'voltage': float(voltage),
                    'current': float(current),
                    'temperature': float(temp),
                    'cv_mode': cv_flag == 'on',
                }
            except Exception as e:
                print(f'[RD6018] Ошибка получения метрик: {e}. Повтор через 10 сек.')
                await asyncio.sleep(10)
        return {
            'voltage': None,
            'current': None,
            'temperature': None,
            'cv_mode': False,
        }

    async def set_params(self, voltage, current):
        await self.hass.set_number(ENTITY_IDS['voltage_set'], voltage)
        await self.hass.set_number(ENTITY_IDS['current_set'], current)

    async def power_off(self):
        await self.hass.turn_off_switch(ENTITY_IDS['output_switch'])
