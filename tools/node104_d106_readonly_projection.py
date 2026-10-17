"""D106 strict, read-only projection of independently sourced trial OFF evidence.

This pure adapter neither polls hardware nor accepts caller-assigned proof fields:
callers must provide fresh HA REST and native ESPHome callback envelopes.
A producer must acquire these envelopes from the real transports independently.
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
# HA102 has the canonical register, setpoint and autonomous entities.
# Lease remaining/TTL/modbus freshness are native ESP-only objects.
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


def project_off(raw: dict, *, now: float | None = None) -> TrialOffProof:
    """Build a D090 proof only from two complete independent current records.

    An HA ButtonInfo inventory is NOT a switch-state reading; required HA
    autonomous and lease fields must be actual, fresh state observations.
    """
    now = time.time() if now is None else _numeric(now)
    if type(raw) is not dict or set(raw) != {
        "captured_at_epoch", "ha102", "esp128", "source_nonces",
    }:
        raise TransactionError("D106 missing/malformed dual-source snapshot")
    captured = _numeric(raw["captured_at_epoch"])
    if not 0 <= now - captured <= MAX_AGE:
        raise TransactionError("D106 snapshot stale")
    nonces = raw["source_nonces"]
    if (type(nonces) not in (tuple, list) or len(nonces) != 2
            or any(type(x) is not str or len(x) < 16 for x in nonces)
            or nonces[0] == nonces[1]):
        raise TransactionError("D106 independent source nonces missing/reused")
    sources = (("HA102", "ha102", "ha102_rest"), ("ESP128", "esp128", "esp_native_api"))
    values = {}
    for label, key, provenance in sources:
        data = raw[key]
        expected_fields = HA_FIELDS if label == "HA102" else FIELDS
        if type(data) is not dict or set(data) != set(expected_fields):
            raise TransactionError("D106 incomplete independent " + label + " evidence")
        values[label] = {field: _field(data, field, provenance, now) for field in expected_fields}
    for label, observed in values.items():
        if (observed["output_r18"] != 0 or observed["protection_r16"] != 0
                or observed["autonomous"] is not False
                or abs(_numeric(observed["voltage_v"])) > .05
                or abs(_numeric(observed["current_a"])) > .05):
            raise TransactionError("D106 unsafe OFF/physical state: " + label)
        if label == "ESP128" and (
                observed["lease_armed"] is not False
                or _numeric(observed["lease_remaining_s"]) != 0
                or _numeric(observed["lease_ttl_s"]) != 900
                or not 0 <= _numeric(observed["modbus_age_s"]) <= 20):
            raise TransactionError("D106 unsafe native lease state")
    ha, esp = values["HA102"], values["ESP128"]
    for key in ("voltage_v", "current_a", "set_voltage_v", "set_current_a", "ovp_v", "ocp_a"):
        if abs(_numeric(ha[key]) - _numeric(esp[key])) > .02:
            raise TransactionError("D106 HA/native disagreement: " + key)
    proof = TrialOffProof(
        captured, False, False, 0.0, 900, 0,
        float(esp["modbus_age_s"]), float(esp["set_voltage_v"]),
        float(esp["set_current_a"]), float(esp["ovp_v"]),
        float(esp["ocp_a"]), uuid.uuid4().hex,
    )
    proof.validate()
    return proof
