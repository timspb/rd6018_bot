"""Data models shared by the telemetry evidence layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TelemetryQualityStatus(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    INVALID = "INVALID"
    MISSING = "MISSING"


@dataclass(frozen=True)
class TelemetryFieldQuality:
    field: str
    status: TelemetryQualityStatus
    timestamp: Optional[float] = None
    age: Optional[float] = None
    source: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("telemetry field name is required")
        if self.age is not None and self.age < 0:
            raise ValueError("telemetry age must not be negative")
