"""MIX-facing view of the shared external temperature integrity monitor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from external_temp_integrity import ExternalTempIntegrityMonitor


@dataclass(frozen=True)
class MixTemperatureDecision:
    stop: bool
    diagnostic_latched: bool
    reason: str = ""


class MixTemperatureIntegrityPolicy:
    """Reuse the shared monitor; do not create a second temperature detector."""

    def __init__(self, monitor: ExternalTempIntegrityMonitor) -> None:
        self.monitor = monitor

    def evaluate(self, live: Mapping[str, Any]) -> MixTemperatureDecision:
        decision = self.monitor.observe(live, hv=True)
        if decision.trip:
            return MixTemperatureDecision(True, self.monitor.latched, decision.detail)
        if self.monitor.latched:
            return MixTemperatureDecision(True, True, self.monitor.latch_reason)
        return MixTemperatureDecision(False, False)
