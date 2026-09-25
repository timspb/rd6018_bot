"""Fields observed in the preserved V1 display surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class LegacyUISnapshot:
    stage: str
    phase: str | None = None
    voltage: float | None = None
    current: float | None = None
    temperature: float | None = None
    timers: Mapping[str, object] = field(default_factory=dict)
    messages: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    faults: tuple[str, ...] = ()
    battery_status: str = ""
    output_enabled: bool | None = None
    output_state: str | None = None
