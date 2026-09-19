"""Minimal pure V3 domain decision engine; no legacy or infrastructure imports."""

from __future__ import annotations

from .contracts import ActuatorIntent, ActuatorOperation, DomainDecision, TelemetrySnapshot
from .safety import SafetyDomain
from .contracts import SafetySignal


class ChargeDomain:
    owner = "V3 Charge Domain"

    def __init__(self, safety: SafetyDomain | None = None) -> None:
        self.safety = safety or SafetyDomain()

    def evaluate(self, telemetry: TelemetrySnapshot, *, trace_id: str) -> DomainDecision:
        signal = SafetySignal("telemetry", telemetry.age_s <= 20.0, "telemetry_fresh" if telemetry.age_s <= 20.0 else "telemetry_stale", trace_id)
        safety = self.safety.decide(signal)
        if safety.action.value == "CONTAIN":
            intent = ActuatorIntent(ActuatorOperation.CONTAINMENT, None, safety.reason, trace_id)
            return DomainDecision("CONTAINMENT_REQUIRED", "safety", safety.reason, trace_id, intent, safety)
        return DomainDecision("READY", "main", "telemetry_accepted", trace_id, None, safety)


__all__ = ["ChargeDomain"]
