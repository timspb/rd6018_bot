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
    value, meta = ro._cached_native_state(esp, inventory, object_id)
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
        "reported_at_epoch": now - age,
    }}


def _fresh_measured_record(field: str, config_key: str,
                           actual_object_id: str | None, observed: dict,
                           now: float) -> dict:
    """Keep exactly the newly observed SensorState, not aliasing NumberState.

    The deployed 8b75 transport exposes SensorInfo and NumberInfo under the
    same `output_voltage`/`output_current` object_id; its last-type cache
    can be NumberState. D091 therefore captures a dedicated fresh callback
    instead of relying on _state_types for these measured registers.
    """
    if not actual_object_id or config_key not in observed:
        raise ro.ProofError("mandatory native measured SensorState missing")
    value, meta = observed[config_key]
    ro._fresh(meta, native=True)
    if meta.get("object_id") != actual_object_id:
        raise ro.ProofError("native measured callback object identity mismatch")
    if meta.get("device_id") is None or type(meta.get("key")) is not int:
        raise ro.ProofError("native measured callback key/device unknown")
    age = ro._number(meta.get("age_s"))
    return {"value": _physical_value(field, value, ha=False),
            "meta": {"source": "esp_native_api", "object_id": field,
                     "actual_object_id": actual_object_id,
                     "native_type": "SensorState",
                     "entity_type": "SensorInfo",
                     "native_key": meta["key"], "device_id": meta["device_id"],
                     "status": "ok", "reported_at_epoch": now - age}}


def _edge_object_id(key: str, mappings: dict[str, str]) -> str:
    """Resolve a legacy 8b75 runtime TTL omission to D091's pinned native ID.

    The installed ESP firmware exposes safety_lease_ttl as a native SensorInfo,
    but the old runtime's edge_entities map omitted edge_lease_ttl. The ID is
    owned by the already reviewed D091 firmware identity contract. Do not
    infer missing command IDs, use HA, or provide any other silent fallback.
    """
    configured = mappings.get(key)
    if configured:
        if key == "edge_lease_ttl" and configured != ro.EXPECTED_EDGE[key]:
            raise ro.ProofError("native TTL mapping conflicts with pinned firmware identity")
        return configured
    if key == "edge_lease_ttl":
        return ro.EXPECTED_EDGE[key]
    raise ro.ProofError("native edge entity mapping absent: " + key)


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
    if ec is None or (
            ec.connection.host and ec.connection.host != ro.EXPECTED_ESP_HOST):
        raise ro.ProofError("node104 HA/native source identity mismatch")
    esp = ESPHomeTransport(ec, config.rd)
    ha = None
    if hc is not None:
        try:
            ha = HA102Transport(hc, config.rd)
        except Exception:
            # The secondary HA route is never needed to attest native ESP.
            ha = None
    try:
        await asyncio.wait_for(esp.discover(), timeout=8)
        device_info = await ro._device_info(esp.client)
        for key, value in (
            ("project_name", ro.EXPECTED_PROJECT),
            ("project_version", ro.EXPECTED_VERSION),
            ("name", ro.EXPECTED_NAME),
            ("model", ro.EXPECTED_MODEL),
        ):
            if device_info.get(key) != value:
                raise ro.ProofError("native ESP device firmware identity mismatch")
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
        measurement_fields = {"output_r18": "output_state",
                              "voltage_v": "voltage", "current_a": "current"}
        for field, config_key in ENTITY.items():
            actual_object_id = ec.entities.get(config_key)
            if field in measurement_fields:
                native[field] = _fresh_measured_record(
                    field, measurement_fields[field], actual_object_id,
                    native_measurements, now)
            else:
                native[field] = _native_record(
                    field, actual_object_id, esp, inventory, now)
        edge_config = getattr(ec, "edge_entities", {})
        for field, config_key in NATIVE_EDGE.items():
            native[field] = _native_record(
                field, _edge_object_id(config_key, edge_config),
                esp, inventory, now)
        # HA REST is a second *route* to ESP, not a second physical source.
        # Collect it best-effort, without allowing HA outage, last_reported
        # lag or disagreement to override valid direct Native API evidence.
        ha_snapshot = {}
        ha_warnings = {}

        async def fetch_ha(field: str):
            entity_id = hc.entities.get(ENTITY[field]) if hc is not None else None
            if ha is None or not entity_id:
                return field, None, "not_configured"
            try:
                state = await asyncio.wait_for(ha._get(entity_id), timeout=2)
                return field, _ha_record(field, entity_id, state, time.time()), None
            except Exception as exc:
                return field, None, type(exc).__name__

        # Run advisory reads concurrently: optional HA must not consume the
        # native proof freshness budget or serially block native admission.
        for field, record, reason in await asyncio.gather(
                *(fetch_ha(field) for field in projection.HA_FIELDS)):
            if record is not None:
                ha_snapshot[field] = record
            else:
                ha_warnings[field] = reason
        captured = time.time()
        snapshot = {
            "captured_at_epoch": captured,
            # Two observation identifiers, NOT two independent sensors.
            "source_nonces": [uuid.uuid4().hex, uuid.uuid4().hex],
            "ha102": ha_snapshot if ha is not None else None,
            "esp128": native,
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
                "authority": "esp_native_api",
                "ha102": "advisory REST cache of SAME ESP; never an independent physical source",
                "esp128": "native ESPHome typed callback monotonic age, per-field",
                "native_device_count": len(ids),
            },
            "ha_advisory": projection.inspect_ha_advisory(snapshot["ha102"], now=captured),
            "ha_warnings": ha_warnings,
        }
    finally:
        await asyncio.gather(*(c.close() for c in (ha, esp) if c is not None),
                             return_exceptions=True)


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
