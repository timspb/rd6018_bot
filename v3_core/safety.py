"""Canonical pure V3 safety domain."""

from __future__ import annotations

from .contracts import SafetyAction, SafetyDecision, SafetySignal


class SafetyDomain:
    owner = "V3 Safety Domain"

    def decide(self, signal: SafetySignal) -> SafetyDecision:
        action = SafetyAction.ALLOW if signal.healthy else SafetyAction.CONTAIN
        return SafetyDecision(action, signal.reason, signal.trace_id, self.owner)


__all__ = ["SafetyDomain"]
