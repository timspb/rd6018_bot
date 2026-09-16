"""Bounded in-memory telemetry history."""

from __future__ import annotations

from collections import deque
from typing import Iterable

from .snapshot import TelemetrySnapshot


class TelemetryHistory:
    def __init__(self, max_samples: int = 600) -> None:
        if max_samples <= 0:
            raise ValueError("telemetry history size must be positive")
        self._samples: deque[TelemetrySnapshot] = deque(maxlen=max_samples)

    def append(self, snapshot: TelemetrySnapshot) -> None:
        self._samples.append(snapshot)

    def window(self, *, since: float | None = None, until: float | None = None) -> tuple[TelemetrySnapshot, ...]:
        return tuple(
            sample for sample in self._samples
            if (since is None or sample.timestamp is not None and sample.timestamp >= since)
            and (until is None or sample.timestamp is not None and sample.timestamp <= until)
        )

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterable[TelemetrySnapshot]:
        return iter(tuple(self._samples))
