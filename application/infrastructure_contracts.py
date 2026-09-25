"""Pure infrastructure observation contracts for EPIC C.

These immutable DTOs are not wired into production composition and do not
contain transport, lease, actuator or persistence behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReadbackObservation:
    """Canonical comparison record for a requested and observed value."""

    requested_value: Any
    observed_value: Any
    timestamp: datetime
    source: str
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


__all__ = ["ReadbackObservation"]
