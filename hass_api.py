"""
hass_api.py — асинхронный клиент Home Assistant API.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from config import ENTITY_MAP, HA_URL, HA_TOKEN

logger = logging.getLogger("rd6018")


class HassClient:
    """Асинхронный клиент для Home Assistant REST API."""

    def __init__(self, base_url: str = HA_URL, token: str = HA_TOKEN) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=10)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers(),
                timeout=self._timeout,
            )
        return self._session

    async def close(self) -> None:
        """Закрыть сессию."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_state(self, entity_id: str) -> Tuple[Any, Dict]:
        """
        Получить состояние сущности.
        Возвращает (state, attributes).
        При ошибке — (None, {}).
        """
        if not self.base_url or not self.token:
            logger.warning("HassClient not configured")
            return None, {}

        url = f"{self.base_url}/api/states/{entity_id}"
        try:
            session = await self._ensure_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error("HA get_state %s: status %d", entity_id, resp.status)
                    return None, {}
                data = await resp.json()
                state = data.get("state")
                attrs = data.get("attributes", {})

                if state is not None and state not in ("unknown", "unavailable", ""):
                    try:
                        state = float(state)
                    except (ValueError, TypeError):
                        pass
                return state, attrs
        except aiohttp.ClientError as ex:
            logger.error("HA get_state %s: %s", entity_id, ex)
            return None, {}
        except Exception as ex:
            logger.error("HA get_state %s: %s", entity_id, ex)
            return None, {}

    async def get_states(self, entity_ids: List[str]) -> Dict[str, Tuple[Any, Dict]]:
        """Получить состояния нескольких сущностей (параллельно)."""
        result: Dict[str, Tuple[Any, Dict]] = {}
        for eid in entity_ids:
            result[eid] = await self.get_state(eid)
        return result

    async def set_value(self, entity_id: str, value: Any) -> bool:
        """Установить значение number.* через number.set_value."""
        if not self.base_url or not self.token:
            return False

        try:
            val = float(value)
        except (ValueError, TypeError):
            logger.error("set_value: invalid value %r", value)
            return False

        url = f"{self.base_url}/api/services/number/set_value"
        payload = {"entity_id": entity_id, "value": val}
        try:
            session = await self._ensure_session()
            async with session.post(url, json=payload) as resp:
                ok = resp.status in (200, 201)
                if not ok:
                    logger.error("HA set_value %s: status %d", entity_id, resp.status)
                return ok
        except Exception as ex:
            logger.error("HA set_value %s: %s", entity_id, ex)
            return False

    async def set_voltage(self, value: float) -> bool:
        """Установить напряжение."""
        return await self.set_value(ENTITY_MAP["set_voltage"], value)

    async def set_current(self, value: float) -> bool:
        """Установить ток."""
        return await self.set_value(ENTITY_MAP["set_current"], value)

    async def set_ovp(self, value: float) -> bool:
        """Установить OVP (Over Voltage Protection)."""
        return await self.set_value(ENTITY_MAP["ovp"], value)

    async def set_ocp(self, value: float) -> bool:
        """Установить OCP (Over Current Protection)."""
        return await self.set_value(ENTITY_MAP["ocp"], value)

    async def turn_on(self, entity_id: Optional[str] = None) -> bool:
        """Включить switch."""
        eid = entity_id or ENTITY_MAP["switch"]
        url = f"{self.base_url}/api/services/switch/turn_on"
        payload = {"entity_id": eid}
        try:
            session = await self._ensure_session()
            async with session.post(url, json=payload) as resp:
                return resp.status in (200, 201)
        except Exception as ex:
            logger.error("HA turn_on %s: %s", eid, ex)
            return False

    async def turn_off(self, entity_id: Optional[str] = None) -> bool:
        """Выключить switch."""
        eid = entity_id or ENTITY_MAP["switch"]
        url = f"{self.base_url}/api/services/switch/turn_off"
        payload = {"entity_id": eid}
        try:
            session = await self._ensure_session()
            async with session.post(url, json=payload) as resp:
                return resp.status in (200, 201)
        except Exception as ex:
            logger.error("HA turn_off %s: %s", eid, ex)
            return False

    async def get_all_live(self) -> Dict[str, Any]:
        """Получить все live-данные для дашборда."""
        keys = ["voltage", "battery_voltage", "current", "power", "ah", "wh", "temp_int", "temp_ext", "is_cv", "is_cc", "switch", "set_voltage", "set_current", "ovp", "ocp", "input_voltage", "uptime"]
        result: Dict[str, Any] = {}
        for key in keys:
            eid = ENTITY_MAP.get(key)
            if not eid:
                continue
            state, _ = await self.get_state(eid)
            result[key] = state
        return result
