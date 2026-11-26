"""
hass_api.py — асинхронный клиент Home Assistant API.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from config import ENTITY_MAP, HA_INSECURE_LOCAL, HA_URL, HA_TOKEN
from rd6018_telemetry import canonicalize_live

logger = logging.getLogger("rd6018")


class HassClient:
    """Raw HA/selected-physical transport adapter; contains no Safety policy."""

    def __init__(self, base_url: str = HA_URL, token: str = HA_TOKEN, *, backend: Any = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=10)
        self._disable_tls_verify = self._looks_like_local_url(self.base_url) and HA_INSECURE_LOCAL
        self._physical_backend = backend
        # Preserve the native read-only button inventory capability only for a
        # backend that actually implements it. HA-only adapters keep the legacy
        # state/existence preflight used by EdgeSafetyLease.
        native_button_info = getattr(backend, "get_button_info", None)
        if not callable(native_button_info):
            native_button_info = getattr(getattr(backend, "transport", None),
                                         "get_button_info", None)
        if callable(native_button_info):
            self.get_button_info = native_button_info

    @classmethod
    def from_physical_config(cls, root: str | None = None) -> "HassClient":
        """Keep one V2 owner while selecting an existing physical connector by config."""
        from runtime.config import load_config
        from runtime.physical.connectors import PhysicalConnectorFactory

        config = load_config(root)
        connector_name = str(config.default_connector or "")
        if not connector_name:
            raise RuntimeError("physical connector selection is not configured")
        connector = PhysicalConnectorFactory(config).create(connector_name)
        # Keep HA REST available as a lease/read sidecar while the selected
        # physical connector remains authoritative for telemetry and writes.
        return cls(HA_URL, HA_TOKEN, backend=connector)

    @property
    def _uses_physical_backend(self) -> bool:
        return self._physical_backend is not None

    @property
    def supports_typed_off_receipt(self) -> bool:
        """Whether the selected connector can return the exact AD051 receipt."""
        return callable(getattr(self._physical_backend, "disable_output_with_receipt", None))

    @property
    def native_connection_generation(self) -> Optional[int]:
        generation = getattr(self._physical_backend, "native_connection_generation", None)
        return generation if isinstance(generation, int) and not isinstance(generation, bool) else None

    async def turn_off_with_receipt(self) -> Any:
        """Return exact connector OFF evidence; unsupported adapters return None."""
        if not self.supports_typed_off_receipt:
            return None
        try:
            return await self._physical_backend.disable_output_with_receipt()
        except Exception as ex:
            logger.error("physical connector typed turn_off failed: %s", ex)
            return None

    @staticmethod
    def _looks_like_local_url(base_url: str) -> bool:
        if not base_url:
            return False
        host = (urlparse(base_url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1", "192.168.1.102"}

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False) if self._disable_tls_verify else None
            self._session = aiohttp.ClientSession(
                headers=self._headers(),
                timeout=self._timeout,
                connector=connector,
            )
        return self._session

    async def close(self) -> None:
        try:
            if self._physical_backend is not None:
                await self._physical_backend.close()
        finally:
            # The selected connector and the independent HA REST sidecar can
            # own separate sessions. Close both even if backend close fails.
            if self._session and not self._session.closed:
                await self._session.close()

    @staticmethod
    def _entity_metadata(entity_id: str, data: Dict[str, Any], status: str) -> Dict[str, Any]:
        last_reported = data.get("last_reported")
        last_updated = data.get("last_updated")
        heartbeat = last_reported if isinstance(last_reported, str) else last_updated
        age_s = None
        if isinstance(heartbeat, str):
            try:
                text = heartbeat[:-1] + "+00:00" if heartbeat.endswith("Z") else heartbeat
                age_s = max(0.0, time.time() - datetime.fromisoformat(text).timestamp())
            except (TypeError, ValueError, OverflowError):
                age_s = None
        return {
            "entity_id": entity_id,
            "status": status,
            "last_reported": last_reported,
            "last_updated": last_updated,
            "last_changed": data.get("last_changed"),
            "age_s": age_s,
        }

    async def get_state(self, entity_id: str) -> Tuple[Any, Dict]:
        """Получить состояние сущности; HA source timestamps сохраняются в attrs."""
        if self._uses_physical_backend:
            reader = getattr(self._physical_backend, "get_state", None)
            if callable(reader):
                return await reader(entity_id)
            # HA remains an independent read sidecar when the selected physical
            # connector has no native entity-state API (e.g. HAESPConnector).
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
                attrs = dict(data.get("attributes", {}))
                attrs["_ha_last_reported"] = data.get("last_reported")
                attrs["_ha_last_updated"] = data.get("last_updated")
                attrs["_ha_last_changed"] = data.get("last_changed")

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

    async def get_native_physical_output_report(self) -> Tuple[Any, Dict[str, Any]] | None:
        """Read native output evidence from the selected physical backend only.

        HA REST state is not a native ESPHome callback and is never a fallback
        for this authority-sensitive read.
        """
        if self._physical_backend is None:
            return None
        reader = getattr(self._physical_backend, "get_physical_output_report", None)
        if not callable(reader):
            return None
        return await reader()

    def get_post_on_native_phase(self, receipt: Any) -> Dict[str, Any]:
        """Return only same-ESPDirectTransport callbacks; HA has no Native proof."""
        from runtime.physical.connectors.esp_direct import ESPDirectConnector

        backend = self._physical_backend
        if not isinstance(backend, ESPDirectConnector):
            return {"status": "NOT_OBSERVED", "reason": "native_backend_unavailable"}
        return backend.get_post_on_native_phase(receipt)

    async def get_native_guard_pre_on_snapshot(self) -> Dict[str, Any] | None:
        """Return the minimal direct ESP callback snapshot used by Guard assessment.

        This deliberately does not fall back to HA or to a fetch timestamp. The
        per-key monotonic timestamp must originate in an ESP Native callback.
        """
        from runtime.physical.connectors.esp_direct import ESPDirectConnector

        backend = self._physical_backend
        if not isinstance(backend, ESPDirectConnector):
            return None
        try:
            live = await backend.get_all_live()
        except Exception:
            return None
        keys = (
            "output_state_code_v2", "set_current_readback_v2",
            "protection_code",
        )
        source_meta = live.get("_meta")
        if not isinstance(source_meta, dict):
            return None
        now_monotonic = time.monotonic()
        selected_meta: Dict[str, Any] = {}
        snapshot: Dict[str, Any] = {}
        for key in keys:
            item = source_meta.get(key)
            if not isinstance(item, dict):
                return None
            updated = item.get("subscription_timestamp_monotonic")
            native_type = item.get("native_type")
            age = (now_monotonic - updated
                   if isinstance(updated, (int, float)) and not isinstance(updated, bool)
                   else None)
            if (item.get("source") != "esp_native_api" or item.get("status") != "ok"
                    or native_type != "SensorState" or age is None
                    or age < 0 or age > 10.0):
                return None
            snapshot[key] = live.get(key)
            selected_meta[key] = {
                "source": "esp_native_api", "status": "ok",
                "native_type": native_type, "age_s": age,
                "subscription_timestamp_monotonic": updated,
            }
        snapshot["_meta"] = selected_meta
        # Keep lease separate from the four electrical Guard inputs. It is
        # copied only when its own callback proves Native provenance/freshness.
        try:
            lease_value, lease_meta = await backend.get_state("safety_lease_armed")
        except Exception:
            return snapshot
        updated = lease_meta.get("subscription_timestamp_monotonic")
        age = (time.monotonic() - updated
               if isinstance(updated, (int, float)) and not isinstance(updated, bool)
               else None)
        if (lease_meta.get("source") == "esp_native_api"
                and lease_meta.get("status") == "ok"
                and lease_meta.get("native_type") == "BinarySensorState"
                and age is not None and 0 <= age <= 10.0):
            snapshot["edge_lease_armed"] = lease_value
            snapshot["_lease_meta"] = {
                "source": "esp_native_api", "status": "ok",
                "native_type": "BinarySensorState", "age_s": age,
                "subscription_timestamp_monotonic": updated,
            }
        return snapshot

    async def get_states(self, entity_ids: List[str]) -> Dict[str, Tuple[Any, Dict]]:
        async def _get_one(eid: str) -> Tuple[str, Tuple[Any, Dict]]:
            return eid, await self.get_state(eid)

        results = await asyncio.gather(*[_get_one(eid) for eid in entity_ids])
        return {eid: state for eid, state in results}

    async def press_button(self, entity_id: str) -> bool:
        """Press a configured physical button through the selected backend."""
        if self._uses_physical_backend:
            press = getattr(self._physical_backend, "press_button", None)
            if not callable(press):
                return False
            return bool(await press(entity_id))
        if not self.base_url or not self.token:
            return False
        try:
            session = await self._ensure_session()
            async with session.post(
                f"{self.base_url}/api/services/button/press",
                json={"entity_id": entity_id},
            ) as response:
                return response.status in (200, 201)
        except Exception as ex:
            logger.error("HA button press %s: %s", entity_id, ex)
            return False

    async def set_value(self, entity_id: str, value: Any) -> bool:
        if self._uses_physical_backend:
            mapping = {
                ENTITY_MAP.get("set_voltage"): self.set_voltage,
                ENTITY_MAP.get("set_current"): self.set_current,
            }
            handler = mapping.get(entity_id)
            return bool(await handler(value)) if handler else False
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
        """Dispatch one raw voltage command to the selected transport."""
        if self._uses_physical_backend:
            try:
                await self._physical_backend.set_voltage(float(value))
                return True
            except Exception as ex:
                logger.error("physical connector voltage write failed: %s", ex)
                return False
        return await self.set_value(ENTITY_MAP["set_voltage"], value)

    async def set_current(self, value: float) -> bool:
        """Dispatch one raw current command to the selected transport."""
        if self._uses_physical_backend:
            try:
                await self._physical_backend.set_current(float(value))
                return True
            except Exception as ex:
                logger.error("physical connector current write failed: %s", ex)
                return False
        return await self.set_value(ENTITY_MAP["set_current"], value)

    async def _switch_service(self, service: str, entity_id: Optional[str] = None) -> bool:
        if self._uses_physical_backend:
            try:
                if service == "turn_on":
                    await self._physical_backend.enable_output()
                elif service == "turn_off":
                    await self._physical_backend.disable_output()
                else:
                    return False
                return True
            except Exception as ex:
                logger.error("physical connector %s failed: %s", service, ex)
                return False
        if not self.base_url or not self.token:
            return False
        eid = entity_id or ENTITY_MAP["switch"]
        url = f"{self.base_url}/api/services/switch/{service}"
        payload = {"entity_id": eid}
        try:
            session = await self._ensure_session()
            async with session.post(url, json=payload) as resp:
                ok = resp.status in (200, 201)
                if not ok:
                    logger.error("HA %s %s: status %d", service, eid, resp.status)
                return ok
        except Exception as ex:
            logger.error("HA %s %s: %s", service, eid, ex)
            return False

    async def turn_on(self, entity_id: Optional[str] = None) -> bool:
        """Issue one raw Output-ON transport command; Safety owns admission and verification."""
        return await self._switch_service("turn_on", entity_id)

    async def turn_off(self, entity_id: Optional[str] = None) -> bool:
        """Issue one raw Output-OFF transport command; Safety owns confirmation."""
        return await self._switch_service("turn_off", entity_id)

    async def _fetch_all_states_bulk(self) -> Optional[Dict[str, Any]]:
        if self._uses_physical_backend:
            return None
        if not self.base_url or not self.token:
            return None
        try:
            session = await self._ensure_session()
            async with session.get(f"{self.base_url}/api/states") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {e["entity_id"]: e for e in data}
        except Exception as ex:
            logger.warning("HA bulk /api/states failed: %s", ex)
            return None

    @staticmethod
    def _parse_entity_state(ent: Dict[str, Any]) -> Tuple[Any, str]:
        state = ent.get("state")
        if state is None or state == "":
            return state, "unknown"
        if str(state).lower() in ("unavailable", "unknown"):
            return state, str(state).lower()
        try:
            return float(state), "ok"
        except (ValueError, TypeError):
            return state, "ok"

    @staticmethod
    def _live_keys() -> List[str]:
        # One authoritative list: all mapped RD entities are available to diagnostics.
        return list(ENTITY_MAP.keys())

    async def get_all_live(self) -> Dict[str, Any]:
        """Return values plus source freshness metadata; prefer corrected V2 sensors."""
        if self._uses_physical_backend:
            return dict(canonicalize_live(await self._physical_backend.get_all_live()))
        keys = self._live_keys()
        result: Dict[str, Any] = {}
        meta: Dict[str, Any] = {}
        bulk = await self._fetch_all_states_bulk()

        if bulk is not None:
            for key in keys:
                eid = ENTITY_MAP.get(key)
                if not eid:
                    continue
                ent = bulk.get(eid)
                if ent is None:
                    result[key] = None
                    meta[key] = {
                        "entity_id": eid,
                        "status": "missing",
                        "last_reported": None,
                        "last_updated": None,
                        "last_changed": None,
                        "age_s": None,
                    }
                    continue
                state, status = self._parse_entity_state(ent)
                result[key] = state
                meta[key] = self._entity_metadata(eid, ent, status)
            result["_meta"] = meta
            return dict(canonicalize_live(result))

        # Fallback uses concurrent per-entity GETs so a bulk-endpoint failure cannot
        # serialize dozens of 10s request timeouts and stall the runtime safety loop.
        now_iso = datetime.now(timezone.utc).isoformat()
        key_entities = [
            (key, ENTITY_MAP.get(key))
            for key in keys
            if ENTITY_MAP.get(key)
        ]
        states = await self.get_states([eid for _, eid in key_entities if eid is not None])
        for key, eid in key_entities:
            assert eid is not None
            state, attrs = states.get(eid, (None, {}))
            result[key] = state
            status = "ok" if state not in (None, "unknown", "unavailable", "") else "unknown"
            metadata = self._entity_metadata(
                eid,
                {
                    "last_reported": attrs.get("_ha_last_reported"),
                    "last_updated": attrs.get("_ha_last_updated"),
                    "last_changed": attrs.get("_ha_last_changed"),
                },
                status,
            )
            metadata["fetched_at"] = now_iso
            meta[key] = metadata
        result["_meta"] = meta
        return dict(canonicalize_live(result))

    async def get_entities_status(self) -> List[Dict[str, Any]]:
        if self._uses_physical_backend:
            live = await self.get_all_live()
            return [{"key": key, "entity_id": key, "state": value, "status": "ok" if value is not None else "unknown", "unit": "", "friendly_name": key} for key, value in live.items() if key != "_meta"]
        if not self.base_url or not self.token:
            return []
        bulk = await self._fetch_all_states_bulk()
        result: List[Dict[str, Any]] = []
        for key, entity_id in ENTITY_MAP.items():
            entry: Dict[str, Any] = {
                "key": key,
                "entity_id": entity_id,
                "state": None,
                "status": "error",
                "unit": "",
                "friendly_name": entity_id.split(".")[-1].replace("_", " "),
            }
            ent = bulk.get(entity_id) if bulk else None
            if ent is not None:
                state = ent.get("state")
                attrs = ent.get("attributes", {})
                entry["state"] = state
                entry["unit"] = attrs.get("unit_of_measurement", "")
                entry["friendly_name"] = attrs.get("friendly_name", entry["friendly_name"])
                if state is None or state == "":
                    entry["status"] = "unknown"
                elif str(state).lower() in ("unavailable", "unknown"):
                    entry["status"] = str(state).lower()
                else:
                    entry["status"] = "ok"
            else:
                try:
                    session = await self._ensure_session()
                    async with session.get(f"{self.base_url}/api/states/{entity_id}") as resp:
                        if resp.status != 200:
                            entry["status"] = "error"
                            entry["state"] = f"HTTP {resp.status}"
                        else:
                            data = await resp.json()
                            state = data.get("state")
                            attrs = data.get("attributes", {})
                            entry["state"] = state
                            entry["unit"] = attrs.get("unit_of_measurement", "")
                            entry["friendly_name"] = attrs.get("friendly_name", entry["friendly_name"])
                            if state is None or state == "":
                                entry["status"] = "unknown"
                            elif str(state).lower() in ("unavailable", "unknown"):
                                entry["status"] = str(state).lower()
                            else:
                                entry["status"] = "ok"
                except Exception as ex:
                    entry["status"] = "error"
                    entry["state"] = str(ex)[:50]
            result.append(entry)
        return result
