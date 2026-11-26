"""Pure normalization boundary for live telemetry reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from rd6018_telemetry import as_bool

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


@dataclass(frozen=True)
class DataLoggerObservation:
    """The legacy data_logger projection of one already-fetched live report.

    This deliberately preserves the loop's established key choices and value
    semantics. It is a read model only; protection policy and effects stay with
    their existing owners.
    """

    battery_voltage_v: float
    output_voltage_v: float
    current_a: float
    power_w: float
    external_temperature_raw: Any
    external_temperature_c: float
    amp_hours: float
    is_cv: bool
    is_cc: bool
    output_switch: Any
    output_on: bool
    battery_mode_on: bool
    input_voltage_v: float
    internal_temperature_c: float
    set_voltage_v: float
    set_current_a: float
    live_context: str


def observe_data_logger_cycle(
    live: Mapping[str, Any], *, manual_active: bool = False,
    manual_mode_label: Any = None,
) -> DataLoggerObservation:
    """Project the current raw report using data_logger's established semantics."""
    def number(value: Any, default: float = 0.0) -> float:
        if value is None or value in ("unknown", "unavailable", ""):
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    battery_v = number(live.get("battery_voltage"))
    output_v = number(live.get("voltage"))
    current = number(live.get("current"))
    power = number(live.get("power"))
    temp_raw = live.get("temp_ext")
    temp_c = number(temp_raw)
    ah = number(live.get("ah"))
    is_cv = as_bool(live.get("is_cv")) is True
    is_cc = as_bool(live.get("is_cc")) is True
    output_switch = live.get("switch")
    output_on = str(output_switch or "").lower() == "on"
    mode = manual_mode_label if manual_active else (
        "CV" if is_cv else ("CC" if is_cc else "режим не подтверждён")
    )
    return DataLoggerObservation(
        battery_voltage_v=battery_v,
        output_voltage_v=output_v,
        current_a=current,
        power_w=power,
        external_temperature_raw=temp_raw,
        external_temperature_c=temp_c,
        amp_hours=ah,
        is_cv=is_cv,
        is_cc=is_cc,
        output_switch=output_switch,
        output_on=output_on,
        battery_mode_on=str(live.get("battery_mode", "")).lower() == "on",
        input_voltage_v=number(live.get("input_voltage")),
        internal_temperature_c=number(live.get("temp_int")),
        set_voltage_v=number(live.get("set_voltage")),
        set_current_a=number(live.get("set_current")),
        live_context=(
            f"📊 Факт: V {battery_v:.2f}В | I {current:.2f}А | T {temp_c:.1f}°C | "
            f"режим {mode}"
        ),
    )


_FIELD_KEYS = {
    "voltage": ("voltage", "battery_voltage"),
    "current": ("current",),
    "input_voltage": ("input_voltage",),
    "power": ("power", "power_v2"),
    "external_temperature": ("temp_ext_v2", "temp_ext"),
    "internal_temperature": ("temp_int_v2", "temp_int"),
    "output_state": ("output_state", "output_state_code_v2", "switch"),
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
        for field in ("programmed_voltage", "programmed_current")
    )
    values["timestamp"] = now
    values["source"] = source
    return TelemetryEvidence(TelemetrySnapshot(**values), tuple(qualities))
