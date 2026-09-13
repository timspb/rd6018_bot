"""Charge Ah accumulation from normalized snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .snapshot import TelemetrySnapshot


@dataclass(frozen=True)
class AccumulatorState:
    accumulated_ah: float = 0.0
    session_started_at: Optional[float] = None
    last_timestamp: Optional[float] = None


class ChargeAccumulator:
    def __init__(self, state: AccumulatorState | None = None) -> None:
        self.state = state or AccumulatorState()

    def start(self, timestamp: float) -> None:
        self.state = AccumulatorState(self.state.accumulated_ah, timestamp, timestamp)

    def add(self, snapshot: TelemetrySnapshot) -> float:
        timestamp, current = snapshot.timestamp, snapshot.current
        if timestamp is None or current is None:
            return self.state.accumulated_ah
        if self.state.session_started_at is None:
            self.start(timestamp)
            return self.state.accumulated_ah
        if self.state.last_timestamp is None or timestamp < self.state.last_timestamp:
            raise ValueError("telemetry timestamps must be monotonic")
        # A positive charging current is integrated with a trapezoid rule.
        # The previous current is deliberately not inferred from history here;
        # callers provide snapshots and this accumulator remains state-only.
        previous_current = getattr(self, "_last_current", float(current))
        delta_ah = max(0.0, (previous_current + float(current)) / 2.0) * (timestamp - self.state.last_timestamp) / 3600.0
        self.state = AccumulatorState(
            self.state.accumulated_ah + delta_ah,
            self.state.session_started_at,
            timestamp,
        )
        self._last_current = float(current)
        return self.state.accumulated_ah

    def reset(self) -> None:
        self.state = AccumulatorState()
        self._last_current = 0.0

    def restore(self, state: AccumulatorState) -> None:
        if state.accumulated_ah < 0:
            raise ValueError("restored Ah must not be negative")
        self.state = state
        self._last_current = 0.0
