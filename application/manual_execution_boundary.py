"""Transition-only bridge to the existing V2 physical owner.

The bridge accepts an already-decided V3 target, requires full identity, uses
the installed V2 guarded setter methods, and verifies canonical readback.  It
does not calculate phases or targets and does not own hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time

from rd6018_telemetry import canonical_programmed_readback, finite_float

from .manual_phase_lifecycle import ManualPhaseDecision


@dataclass(frozen=True)
class ManualExecutionAudit:
    decision_id: str
    intent_id: str
    session_id: str
    trace_id: str
    result: str
    timestamp: float
    reason: str


class ManualExecutionBoundary:
    """Apply a V3 decision through the existing, safety-wrapped V2 owner."""

    def __init__(self, physical_owner) -> None:
        self.physical_owner = physical_owner
        self.audit: list[ManualExecutionAudit] = []

    async def apply(self, decision: ManualPhaseDecision, *, identity) -> bool:
        if identity is None or not identity.session_id or not identity.trace_id:
            return False
        intent_id = decision.execution_intent.intent_id
        timestamp = time()
        try:
            before = await self.physical_owner.get_all_live()
            battery_v = finite_float(before.get("battery_voltage"))
            output = str(before.get("switch", "")).lower() in {"on", "true", "1"}
            if not output or battery_v is None or decision.voltage_v < battery_v:
                self._record(decision, intent_id, identity, "DENIED", "precondition failed", timestamp)
                return False
            if not await self.physical_owner.set_current(decision.current_a):
                self._record(decision, intent_id, identity, "FAILED", "current setter rejected", timestamp)
                return False
            if not await self.physical_owner.set_voltage(decision.voltage_v):
                self._record(decision, intent_id, identity, "FAILED", "voltage setter rejected", timestamp)
                return False
            after = await self.physical_owner.get_all_live()
            read_v = canonical_programmed_readback(after, "set_voltage")
            read_i = canonical_programmed_readback(after, "set_current")
            ok = (
                str(after.get("switch", "")).lower() in {"on", "true", "1"}
                and read_v is not None and read_i is not None
                and abs(read_v - decision.voltage_v) <= 0.08
                and abs(read_i - decision.current_a) <= 0.08
            )
            self._record(decision, intent_id, identity, "VERIFIED" if ok else "FAILED", "readback", timestamp)
            return ok
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._record(decision, intent_id, identity, "FAILED", type(exc).__name__, timestamp)
            return False

    def _record(self, decision, intent_id, identity, result, reason, timestamp) -> None:
        self.audit.append(ManualExecutionAudit(
            decision.decision_id, intent_id, identity.session_id, identity.trace_id,
            result, timestamp, reason,
        ))


__all__ = ["ManualExecutionAudit", "ManualExecutionBoundary"]
