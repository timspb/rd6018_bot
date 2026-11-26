from __future__ import annotations

import os
import time
from datetime import datetime
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
        # A diagnostic snapshot has one timestamp for several HA entities.
        # Use the oldest required source heartbeat, never the HTTP fetch time.
        # Missing or ambiguous source timestamps make the snapshot invalid.
        source_times = []
        required = (
            "output_state", "voltage", "current", "configured_voltage",
            "configured_current", "temperature", "battery_voltage",
        )
        for key in required:
            entity = values.get(key, {})
            heartbeat = entity.get("last_reported") or entity.get("last_updated")
            if not isinstance(heartbeat, str):
                break
            try:
                measured_at = datetime.fromisoformat(
                    heartbeat.replace("Z", "+00:00")
                )
                if measured_at.tzinfo is None:
                    break
                source_times.append(measured_at.timestamp())
            except (ValueError, OverflowError):
                break
        complete = len(source_times) == len(required)
        return HardwareSnapshot(
            min(source_times) if complete else 0.0,
            "connected" if complete else "unknown",
            output_state=state,
            measured_voltage=number("voltage"),
            measured_current=number("current"),
            configured_voltage=number("configured_voltage"),
            configured_current=number("configured_current"),
            temperature=number("temperature"),
            battery_voltage=number("battery_voltage"),
        )

    async def get_live_values(self) -> dict[str, Any]:
        values = {key: await self._get(entity) for key, entity in self.config.entities.items()}
        result = {key: value.get("state") for key, value in values.items()}
        result["output_state_code_v2"] = result.get("output_state")
        result["switch"] = "on" if result.get("output_state") not in (None, 0, 0.0, "0") else "off"
        result["set_voltage_readback_v2"] = result.get("configured_voltage")
        result["set_current_readback_v2"] = result.get("configured_current")
        now = time.time()
        metadata: dict[str, dict[str, Any]] = {}
        for key, item in values.items():
            reported = item.get("last_reported")
            updated = item.get("last_updated")
            source_time = None
            for timestamp in (reported, updated):
                if not isinstance(timestamp, str):
                    continue
                try:
                    source_time = datetime.fromisoformat(
                        timestamp.replace("Z", "+00:00")
                    ).timestamp()
                    break
                except (ValueError, OverflowError):
                    continue
            status = "ok" if (item.get("state") not in
                              (None, "", "unknown", "unavailable") and
                              source_time is not None) else "unknown"
            entry = {
                "status": status,
                "last_reported": reported,
                "last_updated": updated,
                "fetched_at": now,
            }
            if source_time is not None:
                entry["age_s"] = max(0.0, now - source_time)
            metadata[key] = entry

        for alias, source in (
            ("output_state_code_v2", "output_state"),
            ("switch", "output_state"),
            ("set_voltage_readback_v2", "configured_voltage"),
            ("set_current_readback_v2", "configured_current"),
        ):
            metadata[alias] = dict(metadata.get(
                source, {"status": "unknown", "fetched_at": now}
            ))
        result["_meta"] = metadata
        return result

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
        return HardwareCapability(True, True, 0.01, self.rd.max_voltage_v, 0.01, 0.01, self.rd.max_current_a, 0.01, True, True, True)

    async def health_check(self):
        await self._get(next(iter(self.config.entities.values())))
        return {"connected": True, "transport": self.config.name, "read_only": True}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
