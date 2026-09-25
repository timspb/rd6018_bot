"""Read-only telemetry authority adapters for Phase 8.4.

Adapters receive a source reader by dependency injection and normalize its
report into a transport-neutral snapshot.  No source-specific client is
constructed here, and there are intentionally no control methods.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, Protocol


class TelemetrySource(str, Enum):
    ESP_DIRECT = "ESP_DIRECT"
    HA = "HA"
    LAST_KNOWN = "LAST_KNOWN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TelemetrySnapshot:
    voltage: float | None
    current: float | None
    power: float | None
    temperature: float | None
    output_state: bool | None
    timestamp: datetime
    received_at: datetime
    freshness_s: float
    is_fresh: bool
    source: TelemetrySource
    confidence: float

    def __post_init__(self) -> None:
        if self.freshness_s < 0:
            raise ValueError("freshness_s must not be negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


class TelemetryProvider(Protocol):
    """Read-only provider boundary; no control operations are declared."""

    async def read(self) -> TelemetrySnapshot: ...


Reader = Callable[[], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]


class TelemetryAdapterError(RuntimeError):
    pass


def _timestamp(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is not None:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    return fallback


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _ReadOnlyTelemetryAdapter:
    source: TelemetrySource

    def __init__(self, reader: Reader, *, max_age_s: float = 10.0, clock: Callable[[], float] = time.time) -> None:
        if max_age_s < 0:
            raise ValueError("max_age_s must not be negative")
        self._reader = reader
        self._max_age_s = float(max_age_s)
        self._clock = clock

    async def read(self) -> TelemetrySnapshot:
        raw = self._reader()
        if inspect.isawaitable(raw):
            raw = await raw
        if not isinstance(raw, Mapping):
            raise TelemetryAdapterError("telemetry reader must return a mapping")
        received = datetime.fromtimestamp(self._clock(), tz=timezone.utc)
        timestamp = _timestamp(raw.get("timestamp", raw.get("captured_at")), received)
        age = max(0.0, (received - timestamp).total_seconds())
        fresh = age <= self._max_age_s
        voltage = _number(raw.get("voltage", raw.get("measured_voltage")))
        current = _number(raw.get("current", raw.get("measured_current")))
        power = _number(raw.get("power"))
        if power is None and voltage is not None and current is not None:
            power = voltage * current
        return TelemetrySnapshot(
            voltage=voltage,
            current=current,
            power=power,
            temperature=_number(raw.get("temperature", raw.get("temp"))),
            output_state=raw.get("output_state"),
            timestamp=timestamp,
            received_at=received,
            freshness_s=age,
            is_fresh=fresh,
            source=self.source,
            confidence=1.0 if fresh else 0.25,
        )


class HATelemetryAdapter(_ReadOnlyTelemetryAdapter):
    source = TelemetrySource.HA


class ESPDirectTelemetryAdapter(_ReadOnlyTelemetryAdapter):
    source = TelemetrySource.ESP_DIRECT


class TelemetryArbitrator:
    """Select ESP Direct, then HA, then last-known, then unknown."""

    def __init__(self) -> None:
        self._last_known: TelemetrySnapshot | None = None

    def select(
        self,
        *,
        esp_direct: TelemetrySnapshot | None,
        ha: TelemetrySnapshot | None,
        now: datetime | None = None,
    ) -> TelemetrySnapshot:
        current = now or datetime.now(timezone.utc)
        for candidate in (esp_direct, ha):
            if candidate is not None and candidate.is_fresh and candidate.source in {
                TelemetrySource.ESP_DIRECT,
                TelemetrySource.HA,
            }:
                self._last_known = candidate
                return candidate
        if self._last_known is not None:
            age = max(0.0, (current - self._last_known.timestamp).total_seconds())
            return TelemetrySnapshot(
                voltage=self._last_known.voltage,
                current=self._last_known.current,
                power=self._last_known.power,
                temperature=self._last_known.temperature,
                output_state=self._last_known.output_state,
                timestamp=self._last_known.timestamp,
                received_at=current,
                freshness_s=age,
                is_fresh=False,
                source=TelemetrySource.LAST_KNOWN,
                confidence=0.25,
            )
        return TelemetrySnapshot(
            voltage=None,
            current=None,
            power=None,
            temperature=None,
            output_state=None,
            timestamp=current,
            received_at=current,
            freshness_s=0.0,
            is_fresh=False,
            source=TelemetrySource.UNKNOWN,
            confidence=0.0,
        )


__all__ = [
    "TelemetrySource", "TelemetrySnapshot", "TelemetryProvider",
    "TelemetryAdapterError", "HATelemetryAdapter", "ESPDirectTelemetryAdapter",
    "TelemetryArbitrator",
]
