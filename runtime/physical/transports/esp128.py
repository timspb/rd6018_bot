from __future__ import annotations

import os
import time
import asyncio
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

    async def _connect(self):
        key = os.getenv(self.config.connection.key_env or "", "")
        if not key:
            raise RuntimeError("ESPHome encryption key environment variable is not set")
        self.client = APIClient(self.config.connection.host, self.config.connection.port, noise_psk=key)
        await self.client.connect(login=True)
        self.entities, self.services = await self.client.list_entities_services()

    async def discover(self):
        if self.client is None: await self._connect()
        return self.entities

    async def get_snapshot(self):
        if self.client is None: await self._connect()
        states = {}
        def on_state(state):
            key = getattr(state, "key", None) or getattr(state, "object_id", None) or getattr(state, "name", None)
            if key is not None:
                states[str(key)] = getattr(state, "state", None)
        self.client.subscribe_states(on_state)
        await asyncio.sleep(0.5)
        def value(name):
            wanted = self.config.entities.get(name)
            for key, state in states.items():
                if key == wanted or key.endswith(str(wanted)):
                    return state
            return None
        def number(name):
            try: return float(value(name))
            except (TypeError, ValueError): return None
        output = value("output_state")
        output_state = None if output is None else bool(output) if isinstance(output, bool) else bool(float(output))
        return HardwareSnapshot(time.time(), "connected", output_state=output_state, measured_voltage=number("voltage"), measured_current=number("current"), configured_voltage=number("configured_voltage"), configured_current=number("configured_current"), ovp=number("ovp"), ocp=number("ocp"))

    async def get_capabilities(self):
        return HardwareCapability(False, False, 0.01, self.rd.max_voltage_v, 0.01, 0.01, self.rd.max_current_a, 0.01, False, False, False, True, True, True)

    async def health_check(self):
        await self.discover()
        return {"connected": True, "transport": self.config.name, "read_only": True, "entities": len(self.entities)}

    async def close(self):
        if self.client is not None:
            await self.client.disconnect()
