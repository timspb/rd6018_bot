"""Shadow-only telemetry source arbitration.

This module deliberately does not participate in the production safety or actuator
path.  It reads the existing read-only transport contracts, compares their reports,
and exposes the selected observation for diagnostics/dashboard experiments.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping

logger = logging.getLogger("rd6018.runtime.telemetry.authority")


class TelemetrySource(str, Enum):
    ESP_DIRECT = "ESP_DIRECT"
    HA = "HA"
    LAST_KNOWN = "LAST_KNOWN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Immutable source-tagged observation used by shadow consumers only."""

    values: Mapping[str, Any] = field(default_factory=dict)
    source: TelemetrySource = TelemetrySource.UNKNOWN
    timestamp: float | None = None
    age: float | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        if self.age is not None and self.age < 0:
            raise ValueError("telemetry age must not be negative")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("telemetry confidence must be between 0 and 1")


@dataclass(frozen=True)
class TelemetryComparison:
    """Read-only evidence comparing both configured sources."""

    selected: TelemetrySource
    snapshots: Mapping[TelemetrySource, TelemetrySnapshot] = field(default_factory=dict)
    latency_s: Mapping[TelemetrySource, float] = field(default_factory=dict)
    differences: Mapping[str, float | str] = field(default_factory=dict)
    failure_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshots", MappingProxyType(dict(self.snapshots)))
        object.__setattr__(self, "latency_s", MappingProxyType(dict(self.latency_s)))
        object.__setattr__(self, "differences", MappingProxyType(dict(self.differences)))


Reader = Callable[[], Awaitable[Any]]


def _values_from_report(report: Any) -> tuple[dict[str, Any], float | None, bool]:
    # Deliberately use the data shape instead of importing a physical/output package.
    # Telemetry authority must remain composable without importing actuator policy.
    if all(hasattr(report, name) for name in ("timestamp", "connection_state", "measured_voltage")):
        values = {
            "output_state": report.output_state,
            "voltage": report.measured_voltage,
            "current": report.measured_current,
            "configured_voltage": report.configured_voltage,
            "configured_current": report.configured_current,
            "ovp": report.ovp,
            "ocp": report.ocp,
            "temperature": report.temperature,
            "battery_voltage": report.battery_voltage,
            "connection_state": report.connection_state,
        }
        return values, float(report.timestamp), report.connection_state == "connected"
    if isinstance(report, Mapping):
        values = dict(report.get("values", report))
        timestamp = report.get("timestamp")
        try:
            timestamp = None if timestamp is None else float(timestamp)
        except (TypeError, ValueError):
            timestamp = None
        state = str(report.get("connection_state", report.get("status", "connected"))).lower()
        return values, timestamp, state == "connected"
    raise TypeError("telemetry reader must return HardwareSnapshot or mapping")


class RuntimeTelemetryProvider:
    """Collect and arbitrate ESP-direct/HA observations without actuator authority."""

    def __init__(
        self,
        *,
        esp_direct_reader: Reader | Any | None = None,
        ha_reader: Reader | Any | None = None,
        max_age_s: float = 10.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_age_s < 0:
            raise ValueError("telemetry max age must not be negative")
        self.esp_direct_reader = esp_direct_reader
        self.ha_reader = ha_reader
        self.max_age_s = float(max_age_s)
        self._clock = clock
        self._last_known: TelemetrySnapshot | None = None

    async def _read(self, reader: Reader | Any | None) -> Any:
        if reader is None:
            raise RuntimeError("reader_not_configured")
        method = getattr(reader, "get_snapshot", None)
        result = method() if callable(method) else reader()
        return await result if hasattr(result, "__await__") else result

    async def _read_timed(self, reader: Reader | Any | None) -> tuple[Any, float]:
        started = self._clock()
        try:
            return await self._read(reader), max(0.0, self._clock() - started)
        except Exception as exc:
            # Preserve the exception for the normal per-source failure taxonomy while
            # still recording the latency of a failed read.
            return exc, max(0.0, self._clock() - started)

    def _snapshot(self, source: TelemetrySource, report: Any, now: float, latency: float) -> TelemetrySnapshot:
        values, timestamp, connected = _values_from_report(report)
        if timestamp is None:
            timestamp = now
        age = max(0.0, now - timestamp)
        confidence = 1.0 if connected and age <= self.max_age_s else (0.5 if connected else 0.0)
        values = dict(values)
        values["latency_s"] = latency
        return TelemetrySnapshot(values, source, timestamp, age, confidence)

    @staticmethod
    def _diff(left: TelemetrySnapshot, right: TelemetrySnapshot) -> dict[str, float | str]:
        differences: dict[str, float | str] = {}
        for key in ("voltage", "current", "configured_voltage", "configured_current", "ovp", "ocp", "temperature", "battery_voltage"):
            a, b = left.values.get(key), right.values.get(key)
            if a is None or b is None:
                continue
            try:
                delta = float(a) - float(b)
            except (TypeError, ValueError):
                continue
            if delta != 0.0:
                differences[key] = delta
        if left.values.get("output_state") != right.values.get("output_state"):
            differences["output_state"] = f"{left.values.get('output_state')}!={right.values.get('output_state')}"
        return differences

    async def collect(self) -> tuple[TelemetrySnapshot, TelemetryComparison]:
        readers = ((TelemetrySource.ESP_DIRECT, self.esp_direct_reader), (TelemetrySource.HA, self.ha_reader))
        results = await asyncio.gather(*(self._read_timed(reader) for _, reader in readers))
        now = self._clock()
        snapshots: dict[TelemetrySource, TelemetrySnapshot] = {}
        latency: dict[TelemetrySource, float] = {}
        failures: list[str] = []
        for (source, _), (result, elapsed) in zip(readers, results):
            latency[source] = elapsed
            if isinstance(result, Exception):
                failures.append(f"{source.value.lower()}:{type(result).__name__}:{result}")
                continue
            try:
                snapshots[source] = self._snapshot(source, result, now, elapsed)
            except Exception as exc:
                failures.append(f"{source.value.lower()}:invalid:{type(exc).__name__}:{exc}")

        selected = next((snapshots[source] for source in (TelemetrySource.ESP_DIRECT, TelemetrySource.HA)
                         if source in snapshots and snapshots[source].confidence >= 1.0), None)
        if selected is None:
            selected = self._last_known
        if selected is None:
            selected = TelemetrySnapshot(source=TelemetrySource.UNKNOWN, timestamp=now, age=0.0, confidence=0.0)
        elif selected.source != TelemetrySource.LAST_KNOWN:
            self._last_known = selected
        elif self._last_known is not None:
            selected = TelemetrySnapshot(dict(self._last_known.values), TelemetrySource.LAST_KNOWN,
                                          self._last_known.timestamp, max(0.0, now - (self._last_known.timestamp or now)), 0.25)

        comparison = TelemetryComparison(
            selected=selected.source,
            snapshots=snapshots,
            latency_s=latency,
            differences=self._diff(snapshots[TelemetrySource.ESP_DIRECT], snapshots[TelemetrySource.HA])
            if TelemetrySource.ESP_DIRECT in snapshots and TelemetrySource.HA in snapshots else {},
            failure_modes=tuple(failures),
        )
        logger.info("telemetry_shadow selected=%s latency=%s differences=%s failures=%s",
                    comparison.selected.value, dict(comparison.latency_s), dict(comparison.differences), comparison.failure_modes)
        return selected, comparison
