"""Pure readback and receipt predicates for the START transaction."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any


def start_off_receipt_completed_at(receipt: Any, *, receipt_type: type) -> float | None:
    """Return the completion timestamp only for an exact typed OFF/APPLIED receipt."""
    try:
        raw_completed = receipt.terminal_completed_monotonic
    except AttributeError:
        return None
    if isinstance(raw_completed, bool) or not isinstance(raw_completed, (int, float)):
        return None
    try:
        completed = float(raw_completed)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (
        isinstance(receipt, receipt_type) and isinstance(receipt.request_id, str)
        and bool(receipt.request_id)
        and receipt.requested_target is False and receipt.terminal_status == "APPLIED"
        and type(receipt.observed_r18) is int and receipt.observed_r18 == 0
        and type(receipt.connection_generation) is int and math.isfinite(completed)
    ):
        return None
    return completed


def native_off_timestamp_after_receipt(
    report: Any, *, receipt_completed_monotonic: float, connection_generation: int,
) -> float | None:
    """Return a valid post-receipt Native OFF timestamp for the same generation."""
    if not (isinstance(report, tuple) and len(report) == 2):
        return None
    value, meta = report
    if not isinstance(meta, Mapping):
        return None
    timestamp = meta.get("subscription_timestamp_monotonic")
    generation = meta.get("connection_generation")
    if not (
        type(value) is int and value == 0 and meta.get("native_type") == "SensorState"
        and str(meta.get("status", "")).lower() == "ok" and type(generation) is int
        and generation == connection_generation and not isinstance(timestamp, bool)
        and isinstance(timestamp, (int, float)) and math.isfinite(float(timestamp))
        and float(timestamp) > receipt_completed_monotonic
    ):
        return None
    return float(timestamp)


def canonical_candidate_readback_matches(
    candidate_document: Mapping[str, Any], *, generation: int, observed_raw: bytes | None,
    pending_envelope: Mapping[str, Any] | None, read_error: str | None,
) -> bool:
    """Require exact committed candidate bytes and no remaining START_PENDING."""
    if read_error is not None or observed_raw is None or pending_envelope is not None:
        return False
    try:
        observed_document = json.loads(observed_raw.decode("utf-8"))
        expected_document = dict(candidate_document)
        expected_document["start_transaction_generation"] = generation
        expected_raw = json.dumps(
            expected_document, ensure_ascii=False, indent=2, allow_nan=False,
        ).encode("utf-8")
    except (UnicodeError, TypeError, ValueError, OverflowError):
        return False
    return observed_document == expected_document and observed_raw == expected_raw
