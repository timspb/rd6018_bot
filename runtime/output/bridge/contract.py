"""Data contracts for the future V2 actuator bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..intent import SafeOutputIntent


@dataclass(frozen=True)
class LegacyActuatorCommand:
    command: str
    parameters: Mapping[str, float] = None


@dataclass(frozen=True)
class ShadowExecutionRecord:
    intent: SafeOutputIntent
    mapped: LegacyActuatorCommand
    executed: bool
    reason: str
