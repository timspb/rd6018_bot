"""Pure normalization boundary for live telemetry reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .models import TelemetryFieldQuality
from .quality import assess_field
from .snapshot import TelemetrySnapshot


@dataclass(frozen=True)
class TelemetryEvidence:
    """A normalized snapshot together with field-level provenance."""

    snapshot: TelemetrySnapshot
    qualities: tuple[TelemetryFieldQuality, ...] = ()

    def quality(self, field: str) -> TelemetryFieldQuality | None:
        return next((item for item in self.qualities if item.field == field), None)


_FIELD_KEYS = {
    "voltage": ("voltage", "battery_voltage"),
    "current": ("current",),
    "input_voltage": ("input_voltage",),
    "power": ("power", "power_v2"),
    "external_temperature": ("temp_ext_v2", "temp_ext"),
    "internal_temperature": ("temp_int_v2", "temp_int"),
    "output_state": ("output_state", "output_state_code_v2", "switch"),
    "ovp": ("ovp", "ovp_readback_v2"),
    "ocp": ("ocp", "ocp_readback_v2"),
    "protection_status": ("protection_status", "protection_code"),
    "programmed_voltage": ("set_voltage_readback_v2", "set_voltage"),
    "programmed_current": ("set_current_readback_v2", "set_current"),
    "stage": ("stage",),
    "phase": ("phase",),
    "accumulated_ah": ("ah",),
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _output_state(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1"}:
            return True
        if normalized in {"off", "false", "0"}:
            return False
    return None


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return None


def normalize_live(
    live: Mapping[str, Any],
    *,
    now: float,
    source: str = "HA",
    max_age: float | None = 10.0,
) -> TelemetryEvidence:
    """Normalize an already-fetched HA/RD report without performing I/O."""
    metadata = live.get("_meta", {})
    values: dict[str, Any] = {}
    qualities: list[TelemetryFieldQuality] = []
    for field, candidates in _FIELD_KEYS.items():
        key = next((candidate for candidate in candidates if candidate in live), None)
        raw = live.get(key) if key else None
        value = _output_state(raw) if field == "output_state" else (
            raw if field in {"stage", "phase", "protection_status"} else _number(raw)
        )
        values[field] = value
        meta = metadata.get(key, {}) if isinstance(metadata, Mapping) and key else {}
        timestamp = _timestamp(
            meta.get("last_reported", meta.get("last_updated"))
        ) if isinstance(meta, Mapping) else None
        qualities.append(assess_field(
            field, value, timestamp=timestamp, now=now, source=source, max_age=max_age,
        ))

    values["readback_valid"] = all(
        values.get(field) is not None
        for field in ("programmed_voltage", "programmed_current", "ovp", "ocp")
    )
    values["timestamp"] = now
    values["source"] = source
    return TelemetryEvidence(TelemetrySnapshot(**values), tuple(qualities))
