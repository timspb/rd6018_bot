"""Data-only journal models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class JournalEventType(str, Enum):
    PERIODIC = "periodic"
    START = "start"
    TRANSITION = "transition"
    EVIDENCE = "evidence"
    HOLD = "hold"
    SAFETY = "safety"
    TELEMETRY = "telemetry"
    ERROR = "error"


class JournalSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ChargeJournalEntry:
    timestamp: float
    event_type: JournalEventType
    stage: str
    short_message: str
    details: Mapping[str, object] = field(default_factory=dict)
    severity: JournalSeverity = JournalSeverity.INFO

    def __post_init__(self) -> None:
        if not self.stage.strip() or not self.short_message.strip():
            raise ValueError("journal stage and short_message are required")
