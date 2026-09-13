"""Persistence boundary for telemetry evidence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .snapshot import TelemetrySnapshot


class TelemetryRecorder(ABC):
    @abstractmethod
    def record(self, snapshot: TelemetrySnapshot) -> None:
        raise NotImplementedError


class InMemoryTelemetryRecorder(TelemetryRecorder):
    def __init__(self) -> None:
        self.records: list[TelemetrySnapshot] = []

    def record(self, snapshot: TelemetrySnapshot) -> None:
        self.records.append(snapshot)
