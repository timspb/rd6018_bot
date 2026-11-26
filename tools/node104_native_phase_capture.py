"""Optional offline projection for one already-captured ESP Native phase.

This consumes callback records supplied by the existing D106 observer. It does
not subscribe, poll, connect, persist, or authorize an actuator operation.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

MAX_SOURCE_AGE_S = 8.0  # Existing D091/D106 Native freshness bound.
REQUIRED_FIELDS = ("output_r18", "voltage_v", "current_a")


class PhaseCaptureError(ValueError):
    """Input is not a complete, fresh, same-generation Native phase."""


def capture_native_phase(
    records: Mapping[str, Any], *, phase_started_monotonic: float,
    captured_at_monotonic: float,
) -> dict[str, dict[str, Any]]:
    """Project R18/V/I callback records without inventing missing identity.

    ``records`` maps each required field to the existing D106 record envelope
    (``{"value": ..., "meta": ...}``). Timestamps are monotonic seconds from
    the original subscription callback. The returned generation is copied
    verbatim from each callback envelope and must agree across the phase.
    """
    start = _finite(phase_started_monotonic, "phase start")
    captured = _finite(captured_at_monotonic, "capture time")
    if captured < start:
        raise PhaseCaptureError("capture precedes phase start")
    if not isinstance(records, Mapping) or set(records) != set(REQUIRED_FIELDS):
        raise PhaseCaptureError("phase requires exactly R18, voltage and current")

    projected: dict[str, dict[str, Any]] = {}
    generations: set[int] = set()
    devices: set[int] = set()
    keys: set[int] = set()
    for field in REQUIRED_FIELDS:
        record = records[field]
        if type(record) is not dict or set(record) != {"value", "meta"}:
            raise PhaseCaptureError("malformed callback record: " + field)
        meta = record["meta"]
        if type(meta) is not dict or meta.get("source") != "esp_native_api":
            raise PhaseCaptureError("wrong Native callback source: " + field)
        if (meta.get("object_id") != field
                or type(meta.get("actual_object_id")) is not str
                or not meta["actual_object_id"]):
            raise PhaseCaptureError("Native callback entity identity mismatch: " + field)
        if meta.get("native_type") != "SensorState" or meta.get("status") != "ok":
            raise PhaseCaptureError("wrong Native callback type/status: " + field)
        generation = meta.get("connection_generation")
        if type(generation) is not int or generation < 1:
            raise PhaseCaptureError("Native connection generation missing/invalid: " + field)
        device_id, key = meta.get("device_id"), meta.get("native_key")
        if type(device_id) is not int or type(key) is not int or key < 0:
            raise PhaseCaptureError("Native callback key/device missing: " + field)
        timestamp = _finite(meta.get("subscription_timestamp_monotonic"),
                            "callback timestamp: " + field)
        age = captured - timestamp
        if timestamp < start or age < 0 or age > MAX_SOURCE_AGE_S:
            raise PhaseCaptureError("Native callback outside phase/freshness bounds: " + field)
        value = record["value"]
        if field == "output_r18":
            if type(value) is not int or value not in (0, 1):
                raise PhaseCaptureError("invalid Native R18 value")
        else:
            value = _finite(value, "Native measurement: " + field)
        generations.add(generation)
        devices.add(device_id)
        keys.add(key)
        projected[field] = {
            "value": value,
            "source": "esp_native_api",
            "native_type": "SensorState",
            "source_key": key,
            "device_id": device_id,
            "connection_generation": generation,
            "subscription_timestamp_monotonic": timestamp,
            "age_s": age,
        }
    if len(generations) != 1:
        raise PhaseCaptureError("Native callbacks span connection generations")
    if len(devices) != 1 or len(keys) != len(REQUIRED_FIELDS):
        raise PhaseCaptureError("Native callbacks do not identify one ESP/keyed field set")
    return projected


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise PhaseCaptureError("invalid numeric " + label)
    return float(value)
