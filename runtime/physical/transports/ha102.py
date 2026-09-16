from __future__ import annotations

import os
import time
from typing import Any

import aiohttp

from runtime.config.models import PhysicalTransportConfig, RDConfig
from runtime.output.bridge import HardwareCapability, HardwareSnapshot

from .base import ReadOnlyTransport


class HA102Transport(ReadOnlyTransport):
    def __init__(self, config: PhysicalTransportConfig, rd: RDConfig):
        self.config, self.rd = config, rd
        self._session: aiohttp.ClientSession | None = None

    async def _get(self, entity_id: str) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            token = os.getenv(self.config.connection.token_env or "", "")
            if not token:
                raise RuntimeError("HA transport token environment variable is not set")
            self._session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {token}"})
        scheme = "https" if self.config.connection.tls else "http"
        url = f"{scheme}://{self.config.connection.host}:{self.config.connection.port}/api/states/{entity_id}"
        async with self._session.get(url, ssl=False) as response:
            if response.status != 200:
                raise RuntimeError(f"HA read failed: HTTP {response.status}")
            return await response.json()

    async def discover(self):
        return tuple(self.config.entities.values())

    async def get_snapshot(self) -> HardwareSnapshot:
        values = {key: await self._get(entity) for key, entity in self.config.entities.items()}
        def number(key):
            value = values.get(key, {}).get("state")
            try: return float(value)
            except (TypeError, ValueError): return None
        output = values.get("output_state", {}).get("state")
        state = None
        if output is not None:
            normalized = str(output).strip().lower()
            if normalized in {"unknown", "unavailable", "none", ""}:
                state = None
            else:
                try:
                    state = float(normalized) != 0.0
                except ValueError:
                    state = normalized not in {"off", "false", "no"}
        return HardwareSnapshot(time.time(), "connected", output_state=state, measured_voltage=number("voltage"), measured_current=number("current"), configured_voltage=number("configured_voltage"), configured_current=number("configured_current"), ovp=number("ovp"), ocp=number("ocp"), temperature=number("temperature"), battery_voltage=number("battery_voltage"))

    async def disable_output(self) -> None:
        """The only physical write exposed in the first verified-off phase."""
        entity_id = self.config.entities.get("control_output")
        if not entity_id:
            raise RuntimeError("HA output control entity is not configured")
        if self._session is None or self._session.closed:
            token = os.getenv(self.config.connection.token_env or "", "")
            if not token:
                raise RuntimeError("HA transport token environment variable is not set")
            self._session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {token}"})
        scheme = "https" if self.config.connection.tls else "http"
        url = f"{scheme}://{self.config.connection.host}:{self.config.connection.port}/api/services/switch/turn_off"
        async with self._session.post(url, json={"entity_id": entity_id}, ssl=False) as response:
            if response.status not in {200, 201}:
                raise RuntimeError(f"HA disable failed: HTTP {response.status}")

    async def get_capabilities(self):
        return HardwareCapability(True, True, 0.01, self.rd.max_voltage_v, 0.01, 0.01, self.rd.max_current_a, 0.01, True, True, False, True, True, True)

    async def health_check(self):
        await self._get(next(iter(self.config.entities.values())))
        return {"connected": True, "transport": self.config.name, "read_only": True}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
