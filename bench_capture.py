from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, Tuple

from rd6018_telemetry import calibration_fingerprint, finite_float, resolve_regulation


@dataclass(frozen=True)
class CaptureSummary:
    written: int
    duplicate_polls: int
    invalid_polls: int


def _source_timestamp_s(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        timestamp = datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    return timestamp if math.isfinite(timestamp) else None


def source_signature(live: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return None
    values = []
    for key in ("battery_voltage", "current"):
        entry = meta.get(key)
        if not isinstance(entry, Mapping):
            return None
        value = entry.get("last_updated")
        if not isinstance(value, str) or not value.strip():
            return None
        values.append(value.strip())
    return values[0], values[1]


def _optional_finite(live: Mapping[str, Any], key: str) -> Optional[float]:
    return finite_float(live.get(key))


def _optional_text(live: Mapping[str, Any], key: str) -> Optional[str]:
    value = live.get(key)
    if value in (None, "", "unknown", "unavailable"):
        return None
    return str(value)


def build_dynamic_loop_sample(
    live: Mapping[str, Any],
    *,
    phase: str,
    connection_id: str,
    fetched_at_s: Optional[float] = None,
) -> dict[str, Any]:
    """Convert one HA snapshot into a bench JSONL sample.

    The sample timestamp is derived only from HA source timestamps for Vbat/I.
    The local fetch time is retained as context but is never substituted for a
    missing source timestamp.
    """
    phase_text = str(phase).strip()
    connection_text = str(connection_id).strip()
    if not phase_text:
        raise ValueError("phase is required")
    if not connection_text:
        raise ValueError("connection_id is required")

    battery_voltage_v = finite_float(live.get("battery_voltage"))
    current_a = finite_float(live.get("current"))
    if battery_voltage_v is None:
        raise ValueError("battery_voltage is missing/invalid")
    if current_a is None:
        raise ValueError("current is missing/invalid")

    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        raise ValueError("HA source metadata is missing")
    source_times: dict[str, float] = {}
    source_iso: dict[str, str] = {}
    for key in ("battery_voltage", "current"):
        entry = meta.get(key)
        if not isinstance(entry, Mapping):
            raise ValueError(f"source metadata missing for {key}")
        status = str(entry.get("status") or "ok").lower()
        if status != "ok":
            raise ValueError(f"{key} source status={status}")
        raw = entry.get("last_updated")
        parsed = _source_timestamp_s(raw)
        if parsed is None:
            raise ValueError(f"source timestamp missing/invalid for {key}")
        source_times[key] = parsed
        source_iso[key] = str(raw)

    observed_at = max(source_times.values())
    payload: dict[str, Any] = {
        "timestamp_s": observed_at,
        "phase": phase_text,
        "battery_voltage_v": battery_voltage_v,
        "current_a": current_a,
        "connection_id": connection_text,
        "source_timestamps_s": source_times,
        "source_last_updated": source_iso,
        "source_skew_s": max(source_times.values()) - min(source_times.values()),
        "capture_fetched_at_s": time.time() if fetched_at_s is None else float(fetched_at_s),
    }

    optional_numeric = {
        "configured_current_a": _optional_finite(live, "set_current"),
        "output_voltage_v": _optional_finite(live, "voltage"),
        "temp_ext_c": _optional_finite(live, "temp_ext"),
    }
    payload.update({key: value for key, value in optional_numeric.items() if value is not None})

    regulation = resolve_regulation(live).value
    if regulation != "unknown":
        payload["regulation_mode"] = regulation

    for source_key, output_key in (
        ("model_number", "rd_model"),
        ("serial_number", "rd_serial"),
        ("firmware_version", "rd_firmware"),
    ):
        value = _optional_text(live, source_key)
        if value is not None:
            payload[output_key] = value

    fingerprint = calibration_fingerprint(live)
    if fingerprint is not None:
        payload["calibration_fingerprint"] = list(fingerprint)

    return payload


async def capture_dynamic_loop_phase(
    client: Any,
    output_path: Path,
    *,
    phase: str,
    connection_id: str,
    duration_s: float,
    poll_interval_s: float = 0.5,
    max_samples: Optional[int] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CaptureSummary:
    """Append unique HA-source observations to JSONL without actuating hardware."""
    duration = float(duration_s)
    poll = float(poll_interval_s)
    if duration <= 0:
        raise ValueError("duration_s must be > 0")
    if poll < 0:
        raise ValueError("poll_interval_s must be >= 0")
    if max_samples is not None and int(max_samples) < 1:
        raise ValueError("max_samples must be >= 1")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + duration
    last_signature: Optional[Tuple[str, str]] = None
    written = 0
    duplicate_polls = 0
    invalid_polls = 0

    with output_path.open("a", encoding="utf-8") as handle:
        while True:
            live = await client.get_all_live()
            signature = source_signature(live)
            if signature is None:
                invalid_polls += 1
            elif signature == last_signature:
                duplicate_polls += 1
            else:
                try:
                    sample = build_dynamic_loop_sample(
                        live,
                        phase=phase,
                        connection_id=connection_id,
                    )
                except (TypeError, ValueError):
                    invalid_polls += 1
                else:
                    handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
                    handle.flush()
                    written += 1
                    last_signature = signature
                    if max_samples is not None and written >= int(max_samples):
                        break

            now = time.monotonic()
            if now >= deadline:
                break
            await sleep(min(poll, max(0.0, deadline - now)))

    return CaptureSummary(
        written=written,
        duplicate_polls=duplicate_polls,
        invalid_polls=invalid_polls,
    )
