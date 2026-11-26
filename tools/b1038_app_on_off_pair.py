"""Read-only validation for the two existing accepted ExecutionPort callbacks.

This consumes actual ``(OutputCommandReceipt, phase-result)`` callback values.
It performs no collection, command, caching, or persistence. A consistent
source pair is not physical P3 acceptance.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from runtime.output.command_receipt import OutputCommandReceipt


class PairEvidenceError(ValueError):
    """The supplied callbacks do not form a complete consistent pair."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PairEvidenceError(label + " must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise PairEvidenceError(label + " must be finite")
    return number


def _phase(callback: Any, *, target: bool, now: float, max_age_s: float):
    if not isinstance(callback, (tuple, list)) or len(callback) != 2:
        raise PairEvidenceError("missing ExecutionPort callback pair")
    receipt, sample = callback
    if (not isinstance(receipt, OutputCommandReceipt)
            or type(receipt.requested_target) is not bool
            or receipt.requested_target is not target
            or receipt.terminal_status != "APPLIED"
            or type(receipt.observed_r18) is not int
            or receipt.observed_r18 != int(target)
            or type(receipt.connection_generation) is not int
            or receipt.connection_generation < 0
            or not isinstance(receipt.request_id, str) or not receipt.request_id):
        raise PairEvidenceError("callback lacks the exact typed APPLIED target receipt")
    completed = _finite(receipt.terminal_completed_monotonic, "terminal completion")
    if not isinstance(sample, Mapping) or sample.get("status") != "OBSERVED":
        raise PairEvidenceError("Native phase callback is missing or unobserved")
    transport, client = sample.get("source_transport"), sample.get("source_client")
    if transport is None or client is None:
        raise PairEvidenceError("original transport/client references are unavailable")
    records = sample.get("records")
    if not isinstance(records, Mapping):
        raise PairEvidenceError("Native callback records are missing")
    device_ids: set[int] = set()
    times: list[float] = []
    values: dict[str, float] = {}
    expected_fields = ("output_r18", "voltage_v", "current_a")
    for field in expected_fields:
        record = records.get(field)
        if not isinstance(record, Mapping):
            raise PairEvidenceError("Native callback field missing: " + field)
        info, state = record.get("sensor_info"), record.get("state")
        if (info is None or type(info).__name__ != "SensorInfo"
                or state is None or type(state).__name__ != "SensorState"
                or type(state.key) is not int or state.key != getattr(info, "key", None)
                or record.get("native_type") != "SensorState"
                or record.get("source") != "esp_native_api"
                or record.get("status", "ok") != "ok"
                or record.get("object_id") != str(getattr(info, "object_id", None))
                or record.get("key") != info.key
                or type(record.get("device_id")) is not int
                or type(getattr(info, "device_id", None)) is not int
                or record["device_id"] != info.device_id):
            raise PairEvidenceError("raw Native SensorInfo/SensorState provenance is invalid")
        device_ids.add(record["device_id"])
        value = state.state
        if field == "output_r18":
            if type(value) is not int or value != int(target):
                raise PairEvidenceError("Native R18 does not match its receipt")
            values[field] = float(value)
        else:
            values[field] = _finite(value, field)
            if not target and values[field] != 0:
                raise PairEvidenceError("post-OFF measured voltage/current must be zero")
        stamp = _finite(record.get("subscription_timestamp_monotonic"), field + " callback time")
        age = _finite(record.get("age_s"), field + " callback age")
        if stamp <= completed or stamp > now or age < 0 or age > max_age_s or now - stamp > max_age_s:
            raise PairEvidenceError("Native callback is preterminal, future, or stale")
        if record.get("connection_generation") != receipt.connection_generation:
            raise PairEvidenceError("phase callback generation disagrees with its receipt")
        times.append(stamp)
    if len(device_ids) != 1:
        raise PairEvidenceError("Native phase callbacks identify multiple ESP devices")
    return receipt, sample, transport, client, next(iter(device_ids)), completed, min(times), max(times)


def pair_execution_port_callbacks(*, on_callback: Any, off_callback: Any,
                                  now_monotonic: float, max_age_s: float = 8.0) -> dict[str, Any]:
    """Validate actual accepted ON then canonical OFF callback pairs, read-only."""
    now = _finite(now_monotonic, "current monotonic time")
    limit = _finite(max_age_s, "maximum callback age")
    if limit <= 0:
        raise PairEvidenceError("maximum callback age must be positive")
    on = _phase(on_callback, target=True, now=now, max_age_s=limit)
    off = _phase(off_callback, target=False, now=now, max_age_s=limit)
    if on[2] is not off[2] or on[3] is not off[3]:
        raise PairEvidenceError("ON/OFF callbacks came from different transport/client objects")
    if on[0].connection_generation != off[0].connection_generation:
        raise PairEvidenceError("ON/OFF receipts belong to different transport generations")
    if on[4] != off[4]:
        raise PairEvidenceError("ON/OFF callbacks identify different ESP devices")
    if on[5] >= off[5] or on[7] >= off[5] or off[6] <= on[7]:
        raise PairEvidenceError("ON then OFF receipt/callback clock order is invalid")
    if on[0] is off[0]:
        raise PairEvidenceError("ON and OFF callbacks must contain distinct exact receipts")
    return {
        "status": "SOURCE_PAIR_CONSISTENT",
        "physical_p3_status": "NOT_ESTABLISHED_SOURCE_ONLY",
        "same_transport_client_status": "SAME_OBJECTS",
        "clock_domain_status": "SAME_PROCESS_MONOTONIC_ORDER_VALIDATED",
        "device_id": on[4],
        "connection_generation": on[0].connection_generation,
        "on_request_id": on[0].request_id,
        "off_request_id": off[0].request_id,
    }
