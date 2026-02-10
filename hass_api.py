import aiohttp

class HassAPI:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

    async def get_state(self, entity_id):
        url = f'{self.base_url}/api/states/{entity_id}'
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=10) as resp:
                    data = await resp.json()
                    state = data.get('state')
                    # Преобразуем к float если возможно
                    try:
                        state = float(state)
                    except (ValueError, TypeError):
                        pass
                    return state, data.get('attributes', {})
        except Exception as e:
            print(f'[HASS_API] Ошибка получения {entity_id}: {e}')
            return None, {}

    async def set_number(self, entity_id, value):
        url = f'{self.base_url}/api/services/number/set_value'
        payload = {
            'entity_id': entity_id,
            'value': value
        }
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json=payload) as resp:
                return await resp.json()

    async def turn_off_switch(self, entity_id):
        url = f'{self.base_url}/api/services/switch/turn_off'
        payload = {'entity_id': entity_id}
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json=payload) as resp:
                return await resp.json()
