"""D106 live read-only collector: HA102 REST + fresh ESP128 native callbacks.

Source-only observer; no actuator operations, new bot, socket listener,
systemd mutations or trial activation CLI. Reuses D091's actual installed
transport and verified-device functions. No fake fallback is permitted.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

TOOLS = str(Path(__file__).resolve().parent)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import node104_d091_physical_proof_collector as ro
import node104_d106_readonly_projection as projection

# Actual physical register, configured readback and authority entity keys.
ENTITY = {
    "output_r18": "output_state", "voltage_v": "voltage",
    "current_a": "current", "protection_r16": "protection_code",
    "autonomous": "autonomous_mode",
    "set_voltage_v": "configured_voltage", "set_current_a": "configured_current",
    "ovp_v": "ovp", "ocp_a": "ocp",
}
NATIVE_EDGE = {
    "lease_armed": "edge_lease_armed",
    "lease_remaining_s": "edge_lease_remaining",
    "lease_ttl_s": "edge_lease_ttl",
    "modbus_age_s": "edge_modbus_age",
}

# D106 observes the current node104 firmware contract. Keep this identity
# independent of D091's historical default (2.2-autonomous-authority), which
# remains useful to older D090 callers that explicitly pin their release.
EXPECTED_DEVICE_INFO = {
    "project_name": "timspb.rd6018-pb-recovery-v2",
    "project_version": "2.3-ha-canonical",
    "name": "rd6018-controller",
    "model": "esp01_1m",
}


def _validate_device_info(device_info: dict) -> None:
    """Fail closed unless Native API identifies the canonical node104 ESP."""
    if type(device_info) is not dict or any(
            device_info.get(key) != expected
            for key, expected in EXPECTED_DEVICE_INFO.items()):
        raise ro.ProofError("native ESP device firmware identity mismatch")


def _physical_value(field: str, value: object, *, ha: bool) -> object:
    if field == "autonomous" or field == "lease_armed":
        if ha:
            if value not in ("on", "off"):
                raise ro.ProofError("HA binary sensor autonomous_mode missing/unknown")
            return value == "on"
        if type(value) is not bool:
            raise ro.ProofError("native binary SensorState has invalid type")
        return value
    number = ro._ha_number(value) if ha else ro._number(value)
    if field in projection.INTEGER_FIELDS:
        if not number.is_integer():
            raise ro.ProofError("nonintegral raw RD register: " + field)
        return int(number)
    return number


def _ha_record(field: str, entity_id: str, data: dict, now: float) -> dict:
    if not entity_id or type(data) is not dict:
        raise ro.ProofError("missing HA mapped state: " + field)
    ro._ha_freshness(data, now)
    last = data.get("last_reported")
    reported = datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()
    return {"value": _physical_value(field, data.get("state"), ha=True),
            "meta": {"source": "ha102_rest", "object_id": field,
                     "actual_object_id": entity_id, "status": "ok",
                     "reported_at_epoch": reported}}


def _native_record(field: str, object_id: str, esp, inventory, now: float) -> dict:
    if not object_id:
        raise ro.ProofError("missing native entity mapping: " + field)
    expected_entity_type = (
        "BinarySensorInfo" if field == "lease_armed"
        else "NumberInfo" if field in {"set_voltage_v", "set_current_a", "ovp_v", "ocp_a"}
        else "SensorInfo"
    )
    value, meta = ro._cached_native_state(
        esp, inventory, object_id, expected_entity_type=expected_entity_type)
    ro._fresh(meta)
    age = ro._number(meta.get("age_s"))
    if age > ro.MAX_SOURCE_AGE_S:
        raise ro.ProofError("native typed callback stale: " + field)
    value = _physical_value(field, value, ha=False)
    return {"value": value, "meta": {
        "source": "esp_native_api", "object_id": field,
        "actual_object_id": object_id, "native_type": meta.get("native_type"),
        "entity_type": meta.get("entity_type"), "native_key": meta.get("key"),
        "device_id": meta.get("device_id"), "status": "ok",
        "subscription_timestamp_monotonic": meta.get("subscription_timestamp_monotonic"),
        "reported_at_epoch": now - age,
    }}


def _native_callback_record(field: str, callback: tuple, inventory, now: float) -> dict:
    """Build a measurement from its keyed SensorState callback, never the ID cache.

    ESPHome may expose a measured SensorInfo and a configured NumberInfo with
    the same object_id. The transport cache is keyed by object_id and its
    latest type/key can therefore belong to the configured number instead of
    the measured sensor. The fresh callback has an unambiguous native key.
    """
    value, meta = callback
    if type(meta) is not dict or meta.get("source") != "esp_native_api":
        raise ro.ProofError("native measurement callback source mismatch: " + field)
    ro._fresh(meta, native=True)
    age = ro._number(meta.get("age_s"))
    if age > ro.MAX_SOURCE_AGE_S:
        raise ro.ProofError("native typed callback stale: " + field)
    object_id, key, device_id = meta.get("object_id"), meta.get("key"), meta.get("device_id")
    if (type(object_id) is not str or type(key) is not int or type(device_id) is not int
            or meta.get("entity_type") != "SensorInfo"):
        raise ro.ProofError("native measurement callback identity/type mismatch: " + field)
    matches = [entity for entity in inventory
               if getattr(entity, "object_id", None) == object_id
               and getattr(entity, "key", None) == key]
    if (len(matches) != 1 or type(matches[0]).__name__ != "SensorInfo"
            or type(getattr(matches[0], "device_id", None)) is not int
            or matches[0].device_id != device_id):
        raise ro.ProofError("native measurement inventory identity mismatch: " + field)
    timestamp = ro._number(meta.get("subscription_timestamp_monotonic"))
    reported = _physical_value(field, value, ha=False)
    return {"value": reported, "meta": {
        "source": "esp_native_api", "object_id": field,
        "actual_object_id": object_id, "native_type": "SensorState",
        "entity_type": "SensorInfo", "native_key": key,
        "device_id": device_id, "status": "ok",
        "subscription_timestamp_monotonic": timestamp,
        "reported_at_epoch": now - age,
    }}


def _validate_callback_cache_generation(field: str, callback: tuple, cached: dict) -> None:
    """Check callback/cache provenance without equating two different readings.

    The first typed callback is sampled BEFORE the later cache snapshot.
    A newer native callback can legitimately update the sensor in between.
    Compare values only for the same update generation; for a newer
    generation, the final native snapshot and independent HA comparison
    remain the authority. An older/foreign cache is never accepted.
    """
    original, original_meta = callback
    cache_meta = cached["meta"]
    if (original_meta.get("source") != "esp_native_api"
            or cache_meta.get("source") != "esp_native_api"
            or original_meta.get("native_type") != "SensorState"
            or cache_meta.get("native_type") != "SensorState"
            or cache_meta.get("actual_object_id") != original_meta.get("object_id")
            or original_meta.get("key") != cache_meta.get("native_key")
            or original_meta.get("device_id") != cache_meta.get("device_id")):
        raise ro.ProofError("native callback/cache identity or type disagreement: " + field)
    first_ts = ro._number(original_meta.get("subscription_timestamp_monotonic"))
    latest_ts = ro._number(cache_meta.get("subscription_timestamp_monotonic"))
    # The cache update happens in _on_state before the subscribed wrapper
    # observes that same callback (normally microseconds apart).
    same_generation_slack_s = 0.025
    if latest_ts < first_ts - same_generation_slack_s:
        raise ro.ProofError("native cache older than new callback: " + field)
    if abs(latest_ts - first_ts) <= same_generation_slack_s:
        if abs(float(cached["value"]) - ro._number(original)) > 0.02:
            raise ro.ProofError("native same-callback/cache disagreement: " + field)


async def collect_live() -> dict:
    """The actual read-only adapter; requires an installed node104 app/runtime."""
    pid, count = ro._service_identity()
    ro._load_service_environment(pid)
    if str(ro.APP) not in sys.path:
        sys.path.insert(0, str(ro.APP))
    from runtime.config import load_config
    from runtime.physical.transports.ha102 import HA102Transport
    from runtime.physical.transports.esp128 import ESPHomeTransport
    config = load_config(ro.APP / "config")
    if config.default_connector != "esp_direct":
        raise ro.ProofError("pinned node must use esp_direct as configured")
    hc, ec = config.transports.get("ha102"), config.transports.get("esp128")
    if hc is None or ec is None or (
            ec.connection.host and ec.connection.host != ro.EXPECTED_ESP_HOST):
        raise ro.ProofError("node104 HA/native source identity mismatch")
    ha, esp = HA102Transport(hc, config.rd), ESPHomeTransport(ec, config.rd)
    try:
        await asyncio.wait_for(esp.discover(), timeout=8)
        device_info = await ro._device_info(esp.client)
        _validate_device_info(device_info)
        inventory = tuple(esp.entities)
        if not inventory or any(getattr(e, "device_id", None) is None for e in inventory):
            raise ro.ProofError("native inventory lacks pinned device identity")
        ids = {int(e.device_id) for e in inventory}
        if len(ids) != 1:
            raise ro.ProofError("not exactly one physical native device")
        native_measurements = await ro._fresh_measured_sensor_callbacks(
            esp, inventory, ec.entities)
        await asyncio.sleep(0.5)
        now = time.time()
        native = {}
        for field, config_key in ENTITY.items():
            native[field] = _native_record(field, ec.entities.get(config_key),
                                           esp, inventory, now)
        edge_config = getattr(ec, "edge_entities", {})
        for field, config_key in NATIVE_EDGE.items():
            native[field] = _native_record(field, edge_config.get(config_key),
                                           esp, inventory, now)
        # The keyed callback is authoritative for measurements. The ID cache
        # can point at a colliding NumberInfo entry for voltage/current.
        for field, callback in (
            ("output_r18", native_measurements["output_state"]),
            ("voltage_v", native_measurements["voltage"]),
            ("current_a", native_measurements["current"]),
        ):
            native[field] = _native_callback_record(field, callback, inventory, now)
        required_ha = {
            field: hc.entities.get(ENTITY[field]) for field in projection.HA_FIELDS}
        if not all(required_ha.values()):
            raise ro.ProofError("mapped HA read-only entity missing")
        responses = await asyncio.gather(
            *(asyncio.wait_for(ha._get(entity_id), timeout=5)
              for entity_id in required_ha.values()))
        captured = time.time()
        ha_snapshot = {
            field: _ha_record(field, required_ha[field], result, captured)
            for field, result in zip(required_ha, responses)}
        snapshot = {
            "captured_at_epoch": captured,
            "source_nonces": [uuid.uuid4().hex, uuid.uuid4().hex],
            "ha102": ha_snapshot, "esp128": native,
        }
        trial = projection.project_off(snapshot, now=captured)
        # Separate persistence admission is read-only and producer-owned.
        session = Path(os.getenv("RD6018_STATE_DIR",
                              str(ro.ROOT / "state"))) / "charge_session.json"
        if ro._session_state(session) is not False:
            raise ro.ProofError("active/unknown persistent charge session")
        ro._journal_state(session.parent / "session_recovery_quarantine.json")
        return {
            "trial_off_proof": trial._asdict(),
            "observed_pid": pid, "bot_process_count": count,
            "device_info": device_info,
            "d090_journal_exists": (ro.ROOT / "D090_TRANSACTION.json").exists(),
            "source_provenance": {
                "ha102": "HA REST entity last_reported, per-field",
                "esp128": "native ESPHome typed callback monotonic age, per-field",
                "native_device_count": len(ids),
            },
        }
    finally:
        await asyncio.gather(ha.close(), esp.close(), return_exceptions=True)


def main() -> int:
    try:
        value = asyncio.run(asyncio.wait_for(collect_live(), timeout=40))
        print(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except Exception as exc:
        print("D106 read-only proof unavailable: " + type(exc).__name__ + ": " +
              str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())