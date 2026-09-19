"""Session-isolated graph presentation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GraphRange(str, Enum):
    THIRTY_MINUTES = "30m"
    TWO_HOURS = "2h"
    SESSION = "session"
    LOG = "log"


@dataclass(frozen=True)
class GraphSample:
    timestamp: float
    session_id: str
    voltage: float | None
    current: float | None
    battery_temperature: float | None
    fresh: bool = True


@dataclass(frozen=True)
class GraphPoint:
    timestamp: float
    value: float


@dataclass(frozen=True)
class GraphSeries:
    name: str
    unit: str
    points: tuple[GraphPoint, ...]


@dataclass(frozen=True)
class GraphViewModel:
    session_id: str
    selected_range: GraphRange
    voltage: GraphSeries
    current: GraphSeries
    battery_temperature: GraphSeries
    status: str
    graph_reset: bool = True

    @classmethod
    def from_samples(
        cls,
        samples: tuple[GraphSample, ...],
        *,
        session_id: str,
        selected_range: GraphRange = GraphRange.SESSION,
        now: float | None = None,
    ) -> "GraphViewModel":
        if not session_id or session_id == "UNKNOWN":
            return cls.empty(session_id or "UNKNOWN", selected_range, "AMBIGUOUS_SESSION")
        cutoff = None
        if selected_range is GraphRange.THIRTY_MINUTES and now is not None:
            cutoff = now - 30 * 60
        elif selected_range is GraphRange.TWO_HOURS and now is not None:
            cutoff = now - 2 * 60 * 60
        current = tuple(
            sample for sample in samples
            if sample.session_id == session_id
            and sample.fresh
            and (cutoff is None or sample.timestamp >= cutoff)
        )
        current = tuple(sorted(current, key=lambda item: item.timestamp))
        def series(name: str, unit: str, values: tuple[tuple[float, float | None], ...]) -> GraphSeries:
            return GraphSeries(name, unit, tuple(GraphPoint(ts, float(value)) for ts, value in values if value is not None))
        result = cls(
            session_id,
            selected_range,
            series("Voltage", "V", tuple((item.timestamp, item.voltage) for item in current)),
            series("Current", "A", tuple((item.timestamp, item.current) for item in current)),
            series("Battery temperature", "°C", tuple((item.timestamp, item.battery_temperature) for item in current)),
            "READY" if current else "EMPTY_OR_DEGRADED",
            True,
        )
        return result

    @classmethod
    def empty(cls, session_id: str, selected_range: GraphRange, status: str = "EMPTY_OR_DEGRADED") -> "GraphViewModel":
        return cls(
            session_id,
            selected_range,
            GraphSeries("Voltage", "V", ()),
            GraphSeries("Current", "A", ()),
            GraphSeries("Battery temperature", "°C", ()),
            status,
            True,
        )


__all__ = ["GraphPoint", "GraphRange", "GraphSample", "GraphSeries", "GraphViewModel"]
