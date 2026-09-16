"""Data-only replay input models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class TelemetryReplayRecord:
    timestamp: float
    voltage: float | None = None
    current: float | None = None
    temperature: float | None = None
    input_voltage: float | None = None
    accumulated_ah: float | None = None
    output_state: bool | None = None
    quality: str = "valid"
    source: str = "replay"


@dataclass(frozen=True)
class ReplayScenario:
    scenario_id: str
    battery_profile: Any
    recipe: Any
    telemetry: tuple[TelemetryReplayRecord, ...]
    expected_checkpoints: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.telemetry:
            raise ValueError("scenario id and telemetry sequence are required")

