"""Factories for semantic journal events; no presentation formatting."""

from __future__ import annotations

from .models import ChargeJournalEntry, JournalEventType, JournalSeverity


class JournalEventFactory:
    @staticmethod
    def periodic(timestamp: float, stage: str, details: dict[str, object]) -> ChargeJournalEntry:
        return ChargeJournalEntry(timestamp, JournalEventType.PERIODIC, stage, "периодическое состояние", details)

    @staticmethod
    def event(timestamp: float, event_type: JournalEventType, stage: str, message: str, *, details=None, severity=JournalSeverity.INFO) -> ChargeJournalEntry:
        return ChargeJournalEntry(timestamp, event_type, stage, message, details or {}, severity)
