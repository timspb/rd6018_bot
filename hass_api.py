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
from safe_output import (
    EnableResult,
    OutputRequest,
    SafeOutputCoordinator,
    SafetyPolicy,
    SafetySupervisor,
    snapshot_from_live,
)

logger = logging.getLogger("rd6018")

PROGRAMMING_TRANSACTION_TTL_SEC = 30.0
OUTPUT_VERIFY_RETRIES = 5
OUTPUT_VERIFY_DELAY_SEC = 0.20


class HassClient:
    """Асинхронный клиент для Home Assistant REST API."""

    def __init__(self, base_url: str = HA_URL, token: str = HA_TOKEN) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=10)
        self._disable_tls_verify = self._looks_like_local_url(self.base_url) and HA_INSECURE_LOCAL
        self._programming_state: Dict[str, Tuple[float, float]] = {}
        self._safety_supervisor = SafetySupervisor()

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

    async def get_states(self, entity_ids: List[str]) -> Dict[str, Tuple[Any, Dict]]:
        async def _get_one(eid: str) -> Tuple[str, Tuple[Any, Dict]]:
            return eid, await self.get_state(eid)

        results = await asyncio.gather(*[_get_one(eid) for eid in entity_ids])
        return {eid: state for eid, state in results}

    async def set_value(self, entity_id: str, value: Any) -> bool:
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

    def _record_programming(self, key: str, value: float, ok: bool) -> None:
        if ok:
            self._programming_state[key] = (float(value), time.monotonic())
        else:
            self._programming_state.pop(key, None)

    async def _tracked_set(self, key: str, entity_id: str, value: float) -> bool:
        ok = await self.set_value(entity_id, value)
        self._record_programming(key, value, ok)
        return ok

    async def set_voltage(self, value: float) -> bool:
        return await self._tracked_set("voltage", ENTITY_MAP["set_voltage"], value)

    async def set_current(self, value: float) -> bool:
        return await self._tracked_set("current", ENTITY_MAP["set_current"], value)

    async def set_ovp(self, value: float) -> bool:
        return await self._tracked_set("ovp", ENTITY_MAP["ovp"], value)

    async def set_ocp(self, value: float) -> bool:
        return await self._tracked_set("ocp", ENTITY_MAP["ocp"], value)

    def _recent_programming_request(self) -> Optional[OutputRequest]:
        now = time.monotonic()
        required = ("ovp", "ocp", "voltage", "current")
        values: Dict[str, float] = {}
        timestamps: Dict[str, float] = {}
        for key in required:
            item = self._programming_state.get(key)
            if item is None:
                return None
            value, timestamp = item
            if now - timestamp > PROGRAMMING_TRANSACTION_TTL_SEC:
                return None
            values[key] = value
            timestamps[key] = timestamp
        if timestamps["voltage"] < timestamps["ovp"]:
            return None
        return OutputRequest(
            voltage_v=values["voltage"],
            current_a=values["current"],
            ovp_v=values["ovp"],
            ocp_a=values["ocp"],
            recipe_voltage_ceiling_v=self._safety_supervisor.policy.absolute_voltage_ceiling_v,
        )

    def _clear_programming_state(self) -> None:
        self._programming_state.clear()

    async def _switch_service(self, service: str, entity_id: Optional[str] = None) -> bool:
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
        """Fail-closed enable after complete programming transaction + readback."""
        request = self._recent_programming_request()
        if request is None:
            logger.error("HA turn_on blocked: no fresh complete OVP/OCP/V/I programming transaction")
            return False

        before = snapshot_from_live(
            await self.get_all_live(),
            require_programming_freshness=True,
        )
        if before is None:
            logger.error("HA turn_on blocked: required live telemetry is invalid/stale")
            self._clear_programming_state()
            return False
        decision = self._safety_supervisor.preflight(request, before)
        if not decision.allowed:
            logger.error("HA turn_on blocked by safety preflight: %s", decision.detail)
            self._clear_programming_state()
            return False
        verified = self._safety_supervisor.verify_programmed(request, before)
        if not verified.allowed:
            logger.error("HA turn_on blocked by setpoint readback: %s", verified.detail)
            self._clear_programming_state()
            return False

        enabled = await self._switch_service("turn_on", entity_id)
        if not enabled:
            self._clear_programming_state()
            return False

        final = None
        for attempt in range(OUTPUT_VERIFY_RETRIES):
            if attempt:
                await asyncio.sleep(OUTPUT_VERIFY_DELAY_SEC)
            final = snapshot_from_live(
                await self.get_all_live(),
                require_programming_freshness=True,
            )
            if final is not None and final.output_on:
                break

        final_decision = (
            self._safety_supervisor.verify_live_output(request, final)
            if final is not None
            else None
        )
        if final_decision is None or not final_decision.allowed:
            detail = "telemetry invalid/stale" if final_decision is None else final_decision.detail
            logger.error("HA turn_on post-enable verification failed (%s); forcing output OFF", detail)
            await self._switch_service("turn_off", entity_id)
            self._clear_programming_state()
            return False

        self._clear_programming_state()
        return True

    async def turn_off(self, entity_id: Optional[str] = None) -> bool:
        self._clear_programming_state()
        return await self._switch_service("turn_off", entity_id)

    async def safe_enable_output(
        self,
        *,
        voltage_v: float,
        current_a: float,
        ovp_v: float,
        ocp_a: float,
        recipe_voltage_ceiling_v: float,
        policy: Optional[SafetyPolicy] = None,
        readback_delay_s: float = 0.0,
    ) -> EnableResult:
        supervisor = SafetySupervisor(policy or self._safety_supervisor.policy)
        coordinator = SafeOutputCoordinator(self, supervisor, readback_delay_s=readback_delay_s)
        return await coordinator.enable(
            OutputRequest(
                voltage_v=float(voltage_v),
                current_a=float(current_a),
                ovp_v=float(ovp_v),
                ocp_a=float(ocp_a),
                recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
            )
        )

    async def _fetch_all_states_bulk(self) -> Optional[Dict[str, Any]]:
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
