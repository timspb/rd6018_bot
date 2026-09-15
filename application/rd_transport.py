"""Data-only RD transport boundaries for Phase 5.3.

These protocols are declarations only.  They are intentionally not imported by
runtime composition and contain no HA, ESPHome or physical implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Mapping, Protocol


@dataclass(frozen=True)
class RDTelemetry:
    """Transport-neutral measurements returned by an RD reader."""

    voltage: float | None
    current: float | None
    temperature: float | None
    output_state: bool | None
    captured_at: datetime


@dataclass(frozen=True)
class RDReadback:
    """Transport-neutral programmed setpoint/readback snapshot."""

    voltage: float | None
    current: float | None
    output_state: bool | None
    captured_at: datetime


class TelemetryProvider(Protocol):
    """Read-only measurement boundary; never exposes control methods."""

    def read_telemetry(self) -> Awaitable[RDTelemetry]: ...

    def read_output_state(self) -> Awaitable[bool | None]: ...

    def read_readback(self) -> Awaitable[RDReadback]: ...


class ControlProvider(Protocol):
    """Command boundary; domain code must not implement or invoke it."""

    def set_voltage(self, value: float) -> Awaitable[None]: ...

    def set_current(self, value: float) -> Awaitable[None]: ...

    def output_on(self) -> Awaitable[None]: ...

    def output_off(self) -> Awaitable[None]: ...


class RDTransport(TelemetryProvider, ControlProvider, Protocol):
    """Complete transport contract shared by both adapter boundaries."""


class HARDAdapter(RDTransport, Protocol):
    """HA-backed adapter boundary; implementation is intentionally absent."""


class ESPDirectRDAdapter(RDTransport, Protocol):
    """ESP-direct adapter boundary; implementation is intentionally absent."""


__all__ = [
    "RDTelemetry",
    "RDReadback",
    "TelemetryProvider",
    "ControlProvider",
    "RDTransport",
    "HARDAdapter",
    "ESPDirectRDAdapter",
]
