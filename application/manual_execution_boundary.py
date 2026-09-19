"""Transition-only bridge to the existing V2 physical owner.

The bridge accepts an already-decided V3 target, requires full identity, uses
the installed V2 guarded setter methods, and verifies canonical readback.  It
does not calculate phases or targets and does not own hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time

from .manual_phase_lifecycle import ManualPhaseDecision
from .execution_port import ExecutionPort


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
        self.execution_port = physical_owner if isinstance(physical_owner, ExecutionPort) else ExecutionPort(physical_owner)

    @property
    def audit(self):
        return self.execution_port.audit

    async def apply(self, decision: ManualPhaseDecision, *, identity) -> bool:
        if identity is None or not identity.session_id or not identity.trace_id:
            return False
        result = await self.execution_port.apply_intent(decision.execution_intent, identity=identity)
        return result.verified


__all__ = ["ManualExecutionAudit", "ManualExecutionBoundary"]
