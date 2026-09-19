"""In-memory transport for isolated V3 adapter bench tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class BenchScenario(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    WRONG_READBACK = "wrong_readback"
    STALE_STATE = "stale_state"


@dataclass(frozen=True)
class TransportResult:
    accepted: bool
    timed_out: bool
    unavailable: bool
    requested_action: str
    observed_state: Any
    observed_at: datetime | None
    reason: str


class BenchTransport:
    """Deterministic transport simulator; it has no hardware implementation."""

    def __init__(self, scenario: BenchScenario, *, now: datetime | None = None) -> None:
        self.scenario = scenario
        self.now = now or datetime.now(timezone.utc)
        self.commands: list[tuple[str, Any]] = []

    def send(self, action: str, target: Any) -> TransportResult:
        self.commands.append((action, target))
        if self.scenario is BenchScenario.TIMEOUT:
            return TransportResult(False, True, False, action, None, None, "transport_timeout")
        if self.scenario is BenchScenario.UNAVAILABLE:
            return TransportResult(False, False, True, action, None, None, "transport_unavailable")
        if self.scenario is BenchScenario.REJECTED:
            return TransportResult(False, False, False, action, None, self.now, "command_rejected")
        expected = target if action in {"SET_VOLTAGE", "SET_CURRENT"} else action == "OUTPUT_ON"
        observed = expected
        observed_at = self.now
        reason = "transport_accepted"
        if self.scenario is BenchScenario.WRONG_READBACK:
            observed = (float(target) + 1.0) if isinstance(target, (int, float)) else not bool(expected)
            reason = "wrong_readback"
        elif self.scenario is BenchScenario.STALE_STATE:
            observed_at = self.now - timedelta(days=1)
            reason = "stale_readback"
        return TransportResult(True, False, False, action, observed, observed_at, reason)


__all__ = ["BenchScenario", "TransportResult", "BenchTransport"]
