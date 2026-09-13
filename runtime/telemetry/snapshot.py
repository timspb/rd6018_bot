"""Immutable normalized telemetry snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TelemetrySnapshot:
    voltage: Optional[float] = None
    current: Optional[float] = None
    input_voltage: Optional[float] = None
    power: Optional[float] = None
    external_temperature: Optional[float] = None
    internal_temperature: Optional[float] = None
    output_state: Optional[bool] = None
    ovp: Optional[float] = None
    ocp: Optional[float] = None
    protection_status: Optional[str] = None
    programmed_voltage: Optional[float] = None
    programmed_current: Optional[float] = None
    readback_valid: Optional[bool] = None
    stage: Optional[str] = None
    phase: Optional[str] = None
    accumulated_ah: Optional[float] = None
    timestamp: Optional[float] = None
    source: Optional[str] = None
