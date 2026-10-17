"""D106 native-authoritative, read-only projection of trial OFF evidence.

The physical source is one ESP128. Native API is the primary observation path;
HA REST is a cached alternate route to that *same device*, never independent
physical authority or a veto over fresh native readings. Native provenance,
callback freshness and edge containment remain mandatory for D090 trial proof.
No CLI, actuator operation, socket listener or release enablement is defined.
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any

import sys
from pathlib import Path
TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
from node104_d090_transaction import TransactionError, TrialOffProof

FIELDS = (
    "output_r18", "voltage_v", "current_a", "protection_r16",
    "autonomous", "lease_armed", "lease_remaining_s", "lease_ttl_s",
    "modbus_age_s", "set_voltage_v", "set_current_a", "ovp_v", "ocp_a",
)
# HA102 is an optional advisory copy. Lease/TTL/modbus freshness are native-only.
HA_FIELDS = tuple(field for field in FIELDS if field not in
    ("lease_armed", "lease_remaining_s", "lease_ttl_s", "modbus_age_s"))
BOOLEAN_FIELDS = {"autonomous", "lease_armed"}
INTEGER_FIELDS = {"output_r18", "protection_r16"}
MAX_AGE = 8.0


def _numeric(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise TransactionError("D106 missing/nonfinite numeric physical field")
    return float(value)


def _field(source: dict, field: str, source_id: str, now: float) -> Any:
    rec = source.get(field)
    if type(rec) is not dict or set(rec) != {"value", "meta"}:
        raise TransactionError("D106 physical field absent or unknown: " + field)
    meta = rec["meta"]
    if type(meta) is not dict or meta.get("source") != source_id:
        raise TransactionError("D106 source provenance missing/incorrect: " + field)
    reported = _numeric(meta.get("reported_at_epoch"))
    if not 0 <= now - reported <= MAX_AGE:
        raise TransactionError("D106 stale source report: " + field)
    if meta.get("object_id") != field or meta.get("status") != "ok":
        raise TransactionError("D106 source identity/quality incorrect: " + field)
    if source_id == "esp_native_api":
        required_type = "BinarySensorState" if field in BOOLEAN_FIELDS else "SensorState"
        if meta.get("native_type") != required_type:
            raise TransactionError("D106 state callback type mismatch: " + field)
    elif "native_type" in meta:
        raise TransactionError("D106 HA REST record masquerades as native state")
    value = rec["value"]
    if field in BOOLEAN_FIELDS:
        if type(value) is not bool:
            raise TransactionError("D106 unknown/nonboolean edge switch state: " + field)
    elif field in INTEGER_FIELDS:
        if type(value) is not int:
            raise TransactionError("D106 noninteger register: " + field)
    else:
        _numeric(value)
    return value


def inspect_ha_advisory(raw: object, *, now: float | None = None) -> dict[str, object]:
    """Summarize optional HA cache health. This result is NEVER admission authority.

    An old `last_reported` can simply mean an unchanged entity. Missing,
    stale, malformed and contradictory HA cache data cannot veto a fresh,
    correctly identified native callback. Never synthesize HA observations.
    """
    now = time.time() if now is None else _numeric(now)
    if raw is None:
        return {"status": "unavailable", "fresh_fields": 0, "stale_or_invalid_fields": len(HA_FIELDS)}
    if type(raw) is not dict:
        return {"status": "invalid", "fresh_fields": 0, "stale_or_invalid_fields": len(HA_FIELDS)}
    fresh = 0
    for field in HA_FIELDS:
        try:
            _field(raw, field, "ha102_rest", now)
        except TransactionError:
            continue
        fresh += 1
    return {"status": "fresh" if fresh == len(HA_FIELDS) else "partial_or_stale",
            "fresh_fields": fresh, "stale_or_invalid_fields": len(HA_FIELDS) - fresh}


def project_off(raw: dict, *, now: float | None = None) -> TrialOffProof:
    """Build a D090 trial proof exclusively from fresh authoritative ESP128.

    Source nonces identify two capture paths, not two independent sensors.
    HA availability, freshness and agreement are diagnostic only. If native
    callback evidence is missing, stale, invalid or unsafe, fail closed even
    when HA appears fresh/OFF. HA-only operation is NOT a D090 trial proof.
    """
    now = time.time() if now is None else _numeric(now)
    if type(raw) is not dict or set(raw) != {
        "captured_at_epoch", "ha102", "esp128", "source_nonces",
    }:
        raise TransactionError("D106 missing/malformed dual-path snapshot")
    captured = _numeric(raw["captured_at_epoch"])
    if not 0 <= now - captured <= MAX_AGE:
        raise TransactionError("D106 snapshot stale")
    nonces = raw["source_nonces"]
    if (type(nonces) not in (tuple, list) or len(nonces) != 2
            or any(type(x) is not str or len(x) < 16 for x in nonces)
            or nonces[0] == nonces[1]):
        raise TransactionError("D106 capture-path identifiers missing/reused")
    native = raw["esp128"]
    if type(native) is not dict or set(native) != set(FIELDS):
        raise TransactionError("D106 incomplete native ESP128 evidence")
    observed = {field: _field(native, field, "esp_native_api", now) for field in FIELDS}
    if (observed["output_r18"] != 0 or observed["protection_r16"] != 0
            or observed["autonomous"] is not False
            or abs(_numeric(observed["voltage_v"])) > .05
            or abs(_numeric(observed["current_a"])) > .05):
        raise TransactionError("D106 unsafe native OFF/physical state")
    if (observed["lease_armed"] is not False
            or _numeric(observed["lease_remaining_s"]) != 0
            or _numeric(observed["lease_ttl_s"]) != 900
            or not 0 <= _numeric(observed["modbus_age_s"]) <= 20):
        raise TransactionError("D106 unsafe native lease state")
    proof = TrialOffProof(
        captured, False, False, 0.0, 900, 0,
        float(observed["modbus_age_s"]), float(observed["set_voltage_v"]),
        float(observed["set_current_a"]), float(observed["ovp_v"]),
        float(observed["ocp_a"]), uuid.uuid4().hex,
    )
    proof.validate()
    return proof
