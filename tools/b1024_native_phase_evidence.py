"""Offline validator for captured Native Output ON/OFF phase observations.

This module consumes captured values only. It has no transport, actuator,
lease, persistence, or production integration and cannot collect live proof.

Per-transport integer generations are not globally unique session identities.
Validated phase observations therefore do not establish causal linkage between
an Output receipt and callbacks, or between separate ON/OFF phases.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


class EvidenceError(ValueError):
    """Captured evidence is incomplete, ambiguous, stale, or inconsistent."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(label + " must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(label + " must be finite")
    return result


def _phase(receipt: Any, samples: Mapping[str, Any], *, target: bool,
           now_monotonic: float, max_age_s: float) -> tuple[int, int, float, float, float]:
    from runtime.output.command_receipt import OutputCommandReceipt

    if (not isinstance(receipt, OutputCommandReceipt)
            or not isinstance(receipt.request_id, str) or not receipt.request_id
            or receipt.requested_target is not target
            or receipt.terminal_status != "APPLIED"
            or type(receipt.observed_r18) is not int
            or receipt.observed_r18 != int(target)
            or type(receipt.connection_generation) is not int
            or receipt.connection_generation < 0):
        raise EvidenceError("missing, ambiguous, or mismatched typed Output receipt")
    completed = _finite(receipt.terminal_completed_monotonic, "receipt completion")
    if not isinstance(samples, Mapping):
        raise EvidenceError("Native sample map missing")
    identities: set[int] = set()
    timestamps: list[float] = []
    for field, expected in (("output_r18", int(target)),
                            ("voltage_v", None), ("current_a", None)):
        record = samples.get(field)
        if not isinstance(record, Mapping) or set(record) != {"value", "meta"}:
            raise EvidenceError("Native field missing or malformed: " + field)
        value, meta = record["value"], record["meta"]
        if not isinstance(meta, Mapping):
            raise EvidenceError("Native metadata missing: " + field)
        if (meta.get("source") != "esp_native_api"
                or meta.get("native_type") != "SensorState"
                or meta.get("status") != "ok"
                or type(meta.get("device_id")) is not int
                or type(meta.get("connection_generation")) is not int
                or meta["connection_generation"] != receipt.connection_generation):
            raise EvidenceError("Native identity, type, source, or generation mismatch: " + field)
        identities.add(meta["device_id"])
        if field == "output_r18":
            if type(value) is not int or value != expected:
                raise EvidenceError("Native R18 disagrees with phase receipt")
        else:
            numeric = _finite(value, field)
            if not target and numeric != 0:
                raise EvidenceError("post-OFF measured voltage/current must be zero")
        stamp = _finite(meta.get("subscription_timestamp_monotonic"), field + " callback time")
        if stamp <= completed:
            raise EvidenceError("Native callback is not newer than command completion: " + field)
        age = _finite(meta.get("age_s"), field + " age")
        if (age < 0 or age > max_age_s or stamp > now_monotonic
                or not 0 <= now_monotonic - stamp <= max_age_s):
            raise EvidenceError("Native callback stale or from the future: " + field)
        timestamps.append(stamp)
    if len(identities) != 1:
        raise EvidenceError("Native callbacks identify different ESP devices")
    return (receipt.connection_generation, next(iter(identities)), completed,
            min(timestamps), max(timestamps))


def assemble_on_off_evidence(*, on_receipt: Any, on_native: Mapping[str, Any],
                             off_receipt: Any, off_native: Mapping[str, Any],
                             now_monotonic: float, max_age_s: float = 8.0) -> dict[str, Any]:
    """Validate phase shape and return a summary that explicitly lacks causality.

    Freshness uses the existing eight-second physical evidence bound. The
    caller supplies monotonic ages captured by the existing Native observer.
    Receipt/callback clock domains and actual transport-session identity are
    absent from the envelopes, so these checks cannot establish causal proof.
    """
    now = _finite(now_monotonic, "current monotonic time")
    limit = _finite(max_age_s, "maximum evidence age")
    on_generation, on_device, on_completed, on_first, on_last = _phase(
        on_receipt, on_native, target=True, now_monotonic=now, max_age_s=limit)
    off_generation, off_device, off_completed, off_first, _off_last = _phase(
        off_receipt, off_native, target=False, now_monotonic=now, max_age_s=limit)
    if on_generation != off_generation or on_device != off_device:
        raise EvidenceError("ON/OFF phases do not share ESP identity and connection generation")
    if on_completed >= off_completed or on_last >= off_completed or off_first <= on_last:
        raise EvidenceError("ON and OFF receipt/callback timestamps are not ordered")
    return {
        "status": "NATIVE_PHASE_OBSERVATION_PASS",
        "native_phase_observation_status": "PASS",
        "causal_on_off_proof_status": "NOT_PROVEN_MISSING_TRANSPORT_SESSION_IDENTITY",
        "clock_domain_status": "UNVERIFIED_MONOTONIC_CLOCK_DOMAIN",
        "device_id": on_device,
        "connection_generation": on_generation,
        "on_request_id": on_receipt.request_id,
        "off_request_id": off_receipt.request_id,
        "on_native_first_monotonic": on_first,
        "off_native_first_monotonic": off_first,
    }
