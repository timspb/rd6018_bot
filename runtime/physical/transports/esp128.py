from __future__ import annotations

import os
import time
import asyncio
from collections.abc import Callable
from typing import Any

from aioesphomeapi import APIClient

from runtime.config.models import PhysicalTransportConfig, RDConfig
from runtime.output.bridge import HardwareCapability, HardwareSnapshot

from .base import ReadOnlyTransport


class ESPHomeTransport(ReadOnlyTransport):
    def __init__(self, config: PhysicalTransportConfig, rd: RDConfig):
        self.config, self.rd = config, rd
        self.client: APIClient | None = None
        self.entities: tuple[Any, ...] = ()
        self.services: tuple[Any, ...] = ()
        self._entities_by_key: dict[int, list[Any]] = {}
        self._state_cache: dict[str, dict[str, Any]] = {}
        self._state_subscription_remover: Callable[[], None] | None = None
        self._state_subscription_lock = asyncio.Lock()

    async def _connect(self):
        key = os.getenv(self.config.connection.key_env or "", "")
        if not key:
            raise RuntimeError("ESPHome encryption key environment variable is not set")
        self.client = APIClient(self.config.connection.host, self.config.connection.port, None, noise_psk=key)
        await self.client.connect(login=True)
        self.entities, self.services = await self.client.list_entities_services()
        self._entities_by_key = {}
        for entity in self.entities:
            self._entities_by_key.setdefault(int(entity.key), []).append(entity)

    def _on_state(self, state: Any) -> None:
        """Retain only the latest primitive value for each entity."""
        key = getattr(state, "key", None)
        if key is None:
            return
        state_type = type(state).__name__
        value = getattr(state, "state", None)
        for entity in self._entities_by_key.get(int(key), ()):
            object_id = str(entity.object_id)
            self._state_cache.setdefault(object_id, {})[state_type] = value

    async def _ensure_state_subscription(self) -> None:
        """Connect and install at most one state subscription per connection."""
        async with self._state_subscription_lock:
            if self.client is None:
                await self._connect()
            if self._state_subscription_remover is not None:
                return

            self._state_cache.clear()
            remover = self.client.subscribe_states(self._on_state)
            if not callable(remover):
                raise RuntimeError("ESPHome state subscription did not return a remover")
            self._state_subscription_remover = remover

    async def discover(self):
        if self.client is None: await self._connect()
        return self.entities

    async def get_snapshot(self):
        live = await self.get_live_values()
        def number(name):
            try: return float(live.get(name))
            except (TypeError, ValueError): return None
        output = live.get("output_state_code_v2")
        output_state = None if output is None else bool(float(output))
        return HardwareSnapshot(time.time(), "connected", output_state=output_state, measured_voltage=number("voltage"), measured_current=number("current"), configured_voltage=number("configured_voltage"), configured_current=number("configured_current"), ovp=number("ovp"), ocp=number("ocp"), temperature=number("temperature"), battery_voltage=number("battery_voltage"))

    async def get_live_values(self) -> dict[str, Any]:
        await self._ensure_state_subscription()
        await asyncio.sleep(0.5)
        def value(name):
            wanted = self.config.entities.get(name)
            values = self._state_cache.get(str(wanted), {})
            preferred = "SensorState" if name in {"voltage", "current", "temperature", "output_state"} else "NumberState"
            if preferred in values:
                return values[preferred]
            if values:
                return next(reversed(values.values()))
            return None
        result = {key: value(key) for key in self.config.entities}
        result["output_state_code_v2"] = result.get("output_state")
        result["switch"] = "on" if result.get("output_state") not in (None, 0, 0.0, "0") else "off"
        result["set_voltage_readback_v2"] = result.get("configured_voltage")
        result["set_current_readback_v2"] = result.get("configured_current")
        result["ovp_readback_v2"] = result.get("ovp")
        result["ocp_readback_v2"] = result.get("ocp")
        result["temp_int_v2"] = result.get("temp_int")
        result["temp_ext_v2"] = result.get("temp_ext")
        result["power_v2"] = result.get("power")
        now = time.time()
        result["_meta"] = {key: {"status": "ok" if item is not None else "unknown", "age_s": 0.0, "fetched_at": now} for key, item in result.items() if key != "_meta"}
        return result

    async def disable_output(self) -> None:
        """The only physical write exposed in the first verified-off phase."""
        wanted = self.config.entities.get("control_output")
        entity = next((item for item in self.entities if item.object_id == wanted), None)
        if entity is None or self.client is None:
            raise RuntimeError("ESPHome output control entity is not available")
        self.client.switch_command(int(entity.key), False, int(entity.device_id))

    async def get_capabilities(self):
        return HardwareCapability(True, True, 0.01, self.rd.max_voltage_v, 0.01, 0.01, self.rd.max_current_a, 0.01, True, True, False, True, True, True)

    async def health_check(self):
        await self.discover()
        return {"connected": True, "transport": self.config.name, "read_only": True, "entities": len(self.entities)}

    async def close(self):
        remover = self._state_subscription_remover
        self._state_subscription_remover = None
        self._state_cache.clear()
        self.entities = ()
        self.services = ()
        self._entities_by_key.clear()
        client = self.client
        self.client = None
        if remover is not None:
            remover()
        if client is not None:
            await client.disconnect()
