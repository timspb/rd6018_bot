from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone
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
        # Native keys identify callback streams. object_id is not unique across
        # ESPHome domains (for example SensorInfo and NumberInfo can collide).
        self._state_cache: dict[tuple[str, int], dict[str, Any]] = {}
        self._state_updated_at: dict[tuple[str, int], float] = {}
        self._state_reported_at: dict[tuple[str, int], float] = {}
        self._state_types: dict[tuple[str, int], str] = {}
        self._state_subscription_remover: Callable[[], None] | None = None
        self._connection_closed_remover: Callable[[], None] | None = None
        self._state_subscription_lock = asyncio.Lock()

    async def _connect(self):
        key = os.getenv(self.config.connection.key_env or "", "")
        if not key:
            raise RuntimeError("ESPHome encryption key environment variable is not set")
        self.client = APIClient(self.config.connection.host, self.config.connection.port, None, noise_psk=key)
        await self.client.connect(login=True)
        add_closed_callback = getattr(self.client, "add_connection_closed_callback", None)
        if callable(add_closed_callback):
            self._connection_closed_remover = add_closed_callback(self._on_connection_closed)
        self.entities, self.services = await self.client.list_entities_services()
        self._entities_by_key = {}
        for entity in self.entities:
            self._entities_by_key.setdefault(int(entity.key), []).append(entity)

    def _on_connection_closed(self, _event: Any) -> None:
        """Invalidate the cached subscription when aioesphomeapi loses the link."""
        self._state_subscription_remover = None
        self._state_cache.clear()
        self._state_updated_at.clear()
        self._state_reported_at.clear()
        self._state_types.clear()

    async def _ensure_connected(self) -> None:
        client = self.client
        if client is not None and bool(getattr(client, "is_connected", True)):
            return
        if client is not None:
            await self.close()
        await self._connect()

    def _on_state(self, state: Any) -> None:
        """Retain only the latest primitive value for each entity."""
        key = getattr(state, "key", None)
        if key is None:
            return
        state_type = type(state).__name__
        value = getattr(state, "state", None)
        # Compatibility with the existing D061 output guard. Output state is a
        # dedicated sensor; keep its legacy timestamp lookup without sharing
        # voltage/current measurements with number setpoints.
        output_id = self.config.entities.get("output_state")
        if any(str(entity.object_id) == output_id for entity in self._entities_by_key.get(int(key), ())):
            self._state_updated_at[output_id] = time.monotonic()
        expected_info = {"SensorState": "SensorInfo", "NumberState": "NumberInfo",
                         "BinarySensorState": "BinarySensorInfo", "SwitchState": "SwitchInfo",
                         "TextSensorState": "TextSensorInfo"}.get(state_type)
        for entity in self._entities_by_key.get(int(key), ()):
            if type(entity).__name__ != expected_info:
                continue
            identity = (type(entity).__name__, int(entity.key))
            self._state_cache.setdefault(identity, {})[state_type] = value
            self._state_updated_at[identity] = time.monotonic()
            self._state_reported_at[identity] = time.time()
            self._state_types[identity] = state_type

            # Keep the read-only object_id cache shape used by pinned D147/D148
            # collectors. ESPHome object_ids can collide across domains, so
            # measurements own that projection whenever a SensorInfo exists;
            # a colliding NumberState can never replace a measured SensorState.
            object_id = str(entity.object_id)
            candidates = [item for entities in self._entities_by_key.values()
                          for item in entities if str(item.object_id) == object_id]
            sensors = [item for item in candidates if type(item).__name__ == "SensorInfo"]
            legacy_entity = sensors[0] if len(sensors) == 1 else (
                candidates[0] if len(candidates) == 1 else None)
            if legacy_entity is entity:
                self._state_cache[object_id] = {state_type: value}
                self._state_updated_at[object_id] = self._state_updated_at[identity]
                self._state_reported_at[object_id] = self._state_reported_at[identity]
                self._state_types[object_id] = state_type

    def _edge_object_id(self, entity_id: str) -> str | None:
        """Resolve a HA-shaped lease ID to the configured native object ID."""
        configured = self.config.edge_entities
        for object_id in configured.values():
            if entity_id == object_id or entity_id.endswith(f".{object_id}"):
                return object_id
        suffix = str(entity_id).rsplit(".", 1)[-1]
        if suffix in {
            "safety_lease_armed",
            "safety_lease_tripped",
            "safety_boot_quarantine",
            "safety_lease_generation",
            "safety_modbus_age",
            "safety_lease_remaining",
        }:
            return configured.get(
                {
                    "safety_lease_armed": "edge_lease_armed",
                    "safety_lease_tripped": "edge_lease_tripped",
                    "safety_boot_quarantine": "edge_boot_quarantine",
                    "safety_lease_generation": "edge_lease_generation",
                    "safety_modbus_age": "edge_modbus_age",
                    "safety_lease_remaining": "edge_lease_remaining",
                }[suffix],
                suffix,
            )
        for key, object_id in configured.items():
            if entity_id.endswith(str(object_id)):
                return object_id
        return None

    def _read_object_id(self, entity_id: str) -> str | None:
        """Resolve reads only through explicitly configured entity mappings.

        Reads may cover ordinary configured sensors as well as edge entities, but
        native inventory remains closed: a caller cannot probe an arbitrary object.
        Keep this separate from _edge_object_id so the button write whitelist does
        not expand with the read mappings.
        """
        candidate = str(entity_id)
        configured_ids = set(map(str, self.config.entities.values()))
        configured_ids.update(map(str, self.config.edge_entities.values()))
        for object_id in configured_ids:
            # HA may include a registry/device prefix before the ESPHome object ID.
            # This suffix match remains safe because object_id came from the explicit
            # configuration whitelist above.
            if (candidate == object_id or candidate.endswith("." + object_id)
                    or candidate.endswith("_" + object_id)):
                return object_id
        return None

    async def get_entity_state(self, entity_id: str) -> tuple[Any, dict[str, Any]]:
        """Read one native state with its source type and monotonic age."""
        await self._ensure_state_subscription()
        await asyncio.sleep(0.5)
        object_id = self._read_object_id(entity_id)
        domain = str(entity_id).split(".", 1)[0]
        expected = {
            "sensor": "SensorInfo", "number": "NumberInfo",
            "binary_sensor": "BinarySensorInfo", "switch": "SwitchInfo",
        }.get(domain)
        return self._read_subscribed_state(object_id, expected)

    async def get_button_info(self, entity_id: str) -> dict[str, Any]:
        """Read native inventory for one explicitly configured edge button.

        This deliberately uses entity inventory only: it does not subscribe to
        state and cannot invoke a command. Restrict resolution to configured
        ``edge_*`` button mappings so preflight cannot probe arbitrary objects.
        """
        configured_ids = {
            str(object_id) for key, object_id in self.config.edge_entities.items()
            if str(key).startswith("edge_") and str(object_id)
        }
        candidate = str(entity_id)
        object_id = next((item for item in configured_ids
                          if candidate == "button." + item
                          or candidate.endswith("." + item)
                          or candidate.endswith("_" + item)), None)
        if not str(entity_id).startswith("button.") or object_id is None:
            return {"status": "missing", "object_id": None, "native_type": None}
        await self._ensure_connected()
        entity = next((item for item in self.entities
                       if str(item.object_id) == object_id), None)
        if entity is None:
            return {"status": "missing", "object_id": object_id, "native_type": None}
        native_type = type(entity).__name__
        return {
            "status": "ok" if native_type == "ButtonInfo" else "wrong_type",
            "exists": True,
            "object_id": object_id,
            "native_type": native_type,
            "key": int(entity.key),
            "device_id": int(entity.device_id),
        }

    def _read_subscribed_state(self, object_id: str | None,
                               expected_entity_type: str | None = None) -> tuple[Any, dict[str, Any]]:
        matches = [item for item in self.entities
                   if str(item.object_id) == object_id
                   and (expected_entity_type is None
                        or type(item).__name__ == expected_entity_type)]
        entity = matches[0] if len(matches) == 1 else None
        base = {"source": "esp_native_api", "object_id": object_id}
        if object_id is None:
            return None, {**base, "status": "missing", "age_s": None}
        if entity is None:
            has_object_id = any(str(item.object_id) == object_id for item in self.entities)
            return None, {**base, "status": "wrong_entity_type" if has_object_id
                          else "missing", "age_s": None}
        identity = (type(entity).__name__, int(entity.key))
        values = self._state_cache.get(identity, {})
        if not values:
            return None, {
                **base,
                "status": "unknown",
                "native_type": type(entity).__name__,
                "age_s": None,
            }
        state_type = self._state_types.get(identity, "")
        value = values.get(state_type)
        updated = self._state_updated_at.get(identity)
        age_s = None if updated is None else max(0.0, time.monotonic() - updated)
        return value, {
            **base,
            "status": "ok",
            "native_type": state_type,
            "entity_type": type(entity).__name__,
            "age_s": age_s,
            "subscription_timestamp_monotonic": updated,
            "key": int(entity.key),
            "device_id": int(entity.device_id),
        }

    async def get_physical_output_report(self) -> tuple[Any, dict[str, Any]]:
        """Read the configured physical output sensor from the native subscription.

        This is deliberately separate from lease-edge lookup: it is read-only and
        cannot expand the object whitelist used by press_button().
        """
        await self._ensure_state_subscription()
        await asyncio.sleep(0.5)
        object_id = self.config.entities.get("output_state")
        value, meta = self._read_subscribed_state(object_id, "SensorInfo")
        if meta.get("status") != "ok":
            return value, meta
        if meta.get("native_type") != "SensorState":
            return None, {**meta, "status": "wrong_type", "expected_native_type": "SensorState"}
        updated = meta.get("subscription_timestamp_monotonic")
        age_s = (time.monotonic() - updated
                 if isinstance(updated, (int, float)) and not isinstance(updated, bool) else None)
        if age_s is None or not 0 <= age_s <= 8:
            return None, {**meta, "status": "stale", "age_s": age_s}
        if isinstance(value, bool):
            return None, {**meta, "status": "invalid_value", "expected_values": [0, 1]}
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return None, {**meta, "status": "invalid_value", "expected_values": [0, 1]}
        if numeric not in (0.0, 1.0):
            return None, {**meta, "status": "invalid_value", "expected_values": [0, 1]}
        return value, meta

    async def press_button(self, entity_id: str) -> bool:
        """Invoke one explicitly mapped native ESPHome button."""
        await self._ensure_connected()
        object_id = self._edge_object_id(entity_id)
        entity = next((item for item in self.entities if str(item.object_id) == object_id), None)
        if entity is None or self.client is None:
            raise RuntimeError(f"ESPHome edge button is not available: {entity_id}")
        if "button" not in type(entity).__name__.lower():
            raise RuntimeError(f"ESPHome edge entity is not a button: {entity_id}")
        self.client.button_command(int(entity.key), int(entity.device_id))
        return True

    async def _ensure_state_subscription(self) -> None:
        """Connect and install at most one state subscription per connection."""
        async with self._state_subscription_lock:
            await self._ensure_connected()
            if self._state_subscription_remover is not None:
                return

            self._state_cache.clear()
            self._state_updated_at.clear()
            self._state_reported_at.clear()
            self._state_types.clear()
            remover = self.client.subscribe_states(self._on_state)
            # Some aioesphomeapi versions return an unsubscribe callable and
            # others keep this subscription until APIConnection.disconnect().
            # close() bounds the connection lifetime; retain a no-op marker
            # when no remover is provided, avoiding duplicate subscriptions.
            self._state_subscription_remover = remover if callable(remover) else (lambda: None)

    async def discover(self):
        await self._ensure_connected()
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
            expected = "SensorInfo" if name in {
                "voltage", "current", "temperature", "output_state", "protection_code",
                "autonomous_mode", "battery_voltage", "temp_int", "temp_ext", "power",
            } else "NumberInfo"
            return self._read_subscribed_state(self.config.entities.get(name), expected)
        reads = {key: value(key) for key in self.config.entities}
        result = {key: item[0] for key, item in reads.items()}
        result["output_state_code_v2"] = result.get("output_state")
        result["switch"] = "on" if result.get("output_state") not in (None, 0, 0.0, "0") else "off"
        result["set_voltage_readback_v2"] = result.get("configured_voltage")
        result["set_current_readback_v2"] = result.get("configured_current")
        result["ovp_readback_v2"] = result.get("ovp")
        result["ocp_readback_v2"] = result.get("ocp")
        result["temp_int_v2"] = result.get("temp_int")
        result["temp_ext_v2"] = result.get("temp_ext")
        result["power_v2"] = result.get("power")
        # Native state-cache read time is not an ESP sensor heartbeat.
        # The canonical verified-OFF path requires an actual post-command
        # output_state_code_v2 update. Preserve the monotonic subscription
        # timestamp of every source (including derived aliases) instead of
        # advertising every cache read as age=0 / freshly reported.
        aliases = {
            "output_state_code_v2": "output_state",
            "switch": "output_state",
            "set_voltage_readback_v2": "configured_voltage",
            "set_current_readback_v2": "configured_current",
            "ovp_readback_v2": "ovp",
            "ocp_readback_v2": "ocp",
            "temp_int_v2": "temp_int",
            "temp_ext_v2": "temp_ext",
            "power_v2": "power",
        }
        monotonic_now = time.monotonic()
        wall_now = time.time()
        meta = {}
        for name, item in result.items():
            source = aliases.get(name, name)
            object_id = self.config.entities.get(source)
            expected = "SensorInfo" if source in {
                "voltage", "current", "temperature", "output_state", "protection_code",
                "autonomous_mode", "battery_voltage", "temp_int", "temp_ext", "power",
            } else "NumberInfo"
            entity = next((candidate for candidate in self.entities
                           if str(candidate.object_id) == str(object_id)
                           and type(candidate).__name__ == expected), None)
            identity = ((expected, int(entity.key)) if entity is not None else None)
            updated = self._state_updated_at.get(identity)
            age = (monotonic_now - updated
                   if isinstance(updated, (float, int))
                   and not isinstance(updated, bool) else None)
            valid_age = (age is not None and 0 <= age < float('inf'))
            report = {
                "status": "ok" if item is not None and valid_age else "unknown",
                "source": "esp_native_api",
                "native_type": self._state_types.get(identity),
                "age_s": age if valid_age else None,
                "fetched_at": wall_now,
                "source_key": "output_state_code_v2" if source == "output_state" else source,
            }
            selected_meta = reads.get(source, (None, {}))[1]
            for key in ("entity_type", "key", "device_id"):
                if key in selected_meta:
                    report[key] = selected_meta[key]
            if isinstance(updated, (int, float)) and not isinstance(updated, bool):
                report["subscription_timestamp_monotonic"] = updated
            # A stored native callback timestamp must not drift on subsequent
            # cache reads. Otherwise tiny clock-conversion jitter could forge
            # a post-command heartbeat even when the sensor never updated.
            reported_at = self._state_reported_at.get(identity)
            if (valid_age and isinstance(reported_at, (float, int))
                    and not isinstance(reported_at, bool)
                    and 0 < reported_at < float('inf')):
                report["last_reported"] = datetime.fromtimestamp(
                    reported_at, timezone.utc).isoformat()
            meta[name] = report
        result["_meta"] = meta
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
        self._state_updated_at.clear()
        self._state_reported_at.clear()
        self._state_types.clear()
        self.entities = ()
        self.services = ()
        self._entities_by_key.clear()
        client = self.client
        self.client = None
        closed_remover = self._connection_closed_remover
        self._connection_closed_remover = None
        if remover is not None:
            remover()
        if closed_remover is not None:
            closed_remover()
        if client is not None:
            await client.disconnect()