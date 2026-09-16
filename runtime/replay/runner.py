"""Replay execution against injected, non-physical application services."""

from __future__ import annotations

from typing import Any

from .models import ReplayScenario, TelemetryReplayRecord
from .trace import DecisionTrace


class ReplayTelemetryProvider:
    def __init__(self, records: tuple[TelemetryReplayRecord, ...]):
        self.records = records
        self.index = 0

    def __call__(self):
        if self.index >= len(self.records):
            raise StopIteration
        record = self.records[self.index]
        self.index += 1
        return record


class ReplayRunner:
    def __init__(self, orchestrator: Any):
        self.orchestrator = orchestrator

    def run(self, scenario: ReplayScenario) -> tuple[DecisionTrace, ...]:
        provider = getattr(self.orchestrator.context, "telemetry_provider", None)
        if not isinstance(provider, ReplayTelemetryProvider):
            raise ValueError("replay requires ReplayTelemetryProvider")
        traces = []
        for record in scenario.telemetry:
            result = self.orchestrator.tick()
            traces.append(DecisionTrace(
                record.timestamp,
                self._field(result.get("state"), "stage"),
                self._field(result.get("state"), "phase"),
                result.get("telemetry"),
                result.get("charge"), result.get("safety"), result.get("execution"),
                tuple(self.orchestrator.context.journal_recorder.tail(1)),
            ))
        return tuple(traces)

    @staticmethod
    def _field(value, name):
        return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
