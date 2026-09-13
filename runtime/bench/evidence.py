"""Evidence collection without transport or actuator dependencies."""

from __future__ import annotations

from time import time

from .models import BenchEvidenceRecord


class BenchEvidenceRecorder:
    def __init__(self):
        self.records: list[BenchEvidenceRecord] = []

    def add(self, scenario, operator, command, expected, observed, *, readback=None, passed=False, notes=""):
        record = BenchEvidenceRecord(time(), scenario, operator, command, expected, observed, readback, passed, notes)
        self.records.append(record)
        return record

