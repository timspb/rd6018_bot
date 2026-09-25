"""In-memory journal storage for the V3 boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ChargeJournalEntry


class JournalRecorder(ABC):
    @abstractmethod
    def append(self, entry: ChargeJournalEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def tail(self, limit: int = 20) -> tuple[ChargeJournalEntry, ...]:
        raise NotImplementedError


class InMemoryJournalRecorder(JournalRecorder):
    def __init__(self) -> None:
        self._entries: list[ChargeJournalEntry] = []

    def append(self, entry: ChargeJournalEntry) -> None:
        self._entries.append(entry)

    def tail(self, limit: int = 20) -> tuple[ChargeJournalEntry, ...]:
        if limit < 0:
            raise ValueError("limit must not be negative")
        return tuple(self._entries[-limit:] if limit else ())
