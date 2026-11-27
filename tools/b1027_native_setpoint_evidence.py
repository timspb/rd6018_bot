"""Offline validator for captured direct-Native programmed V/I evidence.

This module consumes a real externally captured write receipt and callback
records. It has no transport, actuator, polling, or production integration.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


class EvidenceError(ValueError):
    """Captured setpoint evidence is incomplete or inconsistent."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(label + " must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(label + " must be finite")
    return result


def validate_programmed_setpoints(
    *,
    receipt: Mapping[str, Any],
    native: Mapping[str, Any],
    expected_object_ids: Mapping[str, str],
    now_monotonic: float,
    voltage_tolerance_v: float,
    current_tolerance_a: float,
    voltage_range_v: tuple[float, float],
    current_range_a: tuple[float, float],
    max_age_s: float,
) -> dict[str, Any]:
    """Validate same-device post-write Native Vset/Iset SensorState callbacks.

    ``receipt`` must be captured from the actual programming transaction and
    include its real completion time, generation, requested values, and the
    last callback timestamps observed before writing. This function never
    derives or supplies those fields.
    """
    required_receipt = {
        "request_id", "write_completed_monotonic", "connection_generation",
        "set_voltage_v", "set_current_a", "baseline_voltage_monotonic",
        "baseline_current_monotonic",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != required_receipt:
        raise EvidenceError("real programming receipt is missing or malformed")
    if not isinstance(receipt["request_id"], str) or not receipt["request_id"].strip():
        raise EvidenceError("programming receipt request_id is missing")
    generation = receipt["connection_generation"]
    if type(generation) is not int or generation < 0:
        raise EvidenceError("programming receipt generation is invalid")

    completed = _finite(receipt["write_completed_monotonic"], "write completion")
    baseline_v = _finite(receipt["baseline_voltage_monotonic"], "baseline Vset callback")
    baseline_i = _finite(receipt["baseline_current_monotonic"], "baseline Iset callback")
    expected_v = _finite(receipt["set_voltage_v"], "requested Vset")
    expected_i = _finite(receipt["set_current_a"], "requested Iset")
    now = _finite(now_monotonic, "current monotonic time")
    tol_v = _finite(voltage_tolerance_v, "Vset tolerance")
    tol_i = _finite(current_tolerance_a, "Iset tolerance")
    age_limit = _finite(max_age_s, "maximum evidence age")
    v_min, v_max = (_finite(value, "Vset range") for value in voltage_range_v)
    i_min, i_max = (_finite(value, "Iset range") for value in current_range_a)
    if tol_v < 0 or tol_i < 0 or age_limit < 0 or v_min > v_max or i_min > i_max:
        raise EvidenceError("tolerance, age, or accepted range is invalid")
    if not v_min <= expected_v <= v_max or not i_min <= expected_i <= i_max:
        raise EvidenceError("requested setpoint is outside the accepted physical range")
    if not isinstance(native, Mapping):
        raise EvidenceError("Native sample map missing")
    expected_ids = {
        "configured_voltage": expected_object_ids.get("configured_voltage"),
        "configured_current": expected_object_ids.get("configured_current"),
    } if isinstance(expected_object_ids, Mapping) else {}
    if any(not isinstance(value, str) or not value for value in expected_ids.values()):
        raise EvidenceError("configured Native object IDs are missing")

    identities: set[int] = set()
    result_values: dict[str, float] = {}
    timestamps: dict[str, float] = {}
    for field, expected, baseline, tolerance, bounds in (
        ("configured_voltage", expected_v, baseline_v, tol_v, (v_min, v_max)),
        ("configured_current", expected_i, baseline_i, tol_i, (i_min, i_max)),
    ):
        record = native.get(field)
        if not isinstance(record, Mapping) or set(record) != {"value", "meta"}:
            raise EvidenceError("Native setpoint record missing or malformed: " + field)
        meta = record["meta"]
        if not isinstance(meta, Mapping):
            raise EvidenceError("Native metadata missing: " + field)
        if (meta.get("source") != "esp_native_api"
                or meta.get("status") != "ok"
                or meta.get("native_type") != "SensorState"
                or type(meta.get("device_id")) is not int
                or type(meta.get("connection_generation")) is not int
                or meta["connection_generation"] != generation
                or meta.get("object_id") != expected_ids[field]
                or type(meta.get("key")) is not int):
            raise EvidenceError("Native source, type, identity, or generation mismatch: " + field)
        identities.add(meta["device_id"])
        value = _finite(record["value"], field)
        if not bounds[0] <= value <= bounds[1]:
            raise EvidenceError("Native setpoint is outside the accepted physical range: " + field)
        if abs(value - expected) > tolerance:
            raise EvidenceError("Native programmed setpoint does not match transaction: " + field)
        stamp = _finite(meta.get("subscription_timestamp_monotonic"), field + " callback time")
        age = _finite(meta.get("age_s"), field + " age")
        if stamp <= baseline or stamp <= completed:
            raise EvidenceError("Native callback did not advance after write: " + field)
        if stamp > now or age < 0 or age > age_limit or not 0 <= now - stamp <= age_limit:
            raise EvidenceError("Native callback is stale or from the future: " + field)
        result_values[field] = value
        timestamps[field] = stamp
    if len(identities) != 1:
        raise EvidenceError("Native callbacks identify different ESP devices")
    return {
        "status": "SOURCE_EVIDENCE_VALIDATED",
        "request_id": receipt["request_id"],
        "device_id": next(iter(identities)),
        "connection_generation": generation,
        "set_voltage_v": result_values["configured_voltage"],
        "set_current_a": result_values["configured_current"],
        "native_callback_monotonic": timestamps,
    }
