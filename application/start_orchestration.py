"""Canonical START orchestration above the existing V2 execution handoff."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any, Mapping

from .intents import OperatorIntent
from .production_start_execution_port import (
    ProductionStartExecutionPort,
    ProductionStartMode,
    ProductionStartPortResult,
)
from .start_authority import StartAuthority, StartAuthorityDecision, StartIdentity


@dataclass(frozen=True)
class StartAuditEvent:
    event_type: str
    identity: StartIdentity
    timestamp: float


@dataclass(frozen=True)
class StartOrchestrationResult:
    accepted: bool
    identity: StartIdentity
    reason: str
    authority: StartAuthorityDecision
    port_result: ProductionStartPortResult | None = None
    audit: tuple[StartAuditEvent, ...] = ()


class StartOrchestration:
    """Route an authorized START through one mode-independent handoff."""

    def __init__(
        self,
        authority: StartAuthority,
        port: ProductionStartExecutionPort,
        *,
        mode: ProductionStartMode,
    ) -> None:
        self.authority = authority
        self.port = port
        self.mode = mode

    async def submit(self, intent: OperatorIntent) -> StartOrchestrationResult:
        decision = await self.authority.authorize(intent)
        events: list[StartAuditEvent] = [
            StartAuditEvent(
                "START_AUTHORIZED" if decision.accepted else "START_DENIED",
                decision.identity,
                time(),
            )
        ]
        if not decision.accepted or decision.plan is None:
            return StartOrchestrationResult(
                False,
                decision.identity,
                decision.reason,
                decision,
                audit=tuple(events),
            )
        metadata = {
            "source": intent.source,
            "operator": intent.user,
            "intent": intent.parameters["intent"],
            "condition": intent.parameters["condition"],
            "correlation_metadata": {
                "request_id": decision.identity.request_id,
                "session_id": decision.identity.session_id,
                "trace_id": decision.identity.trace_id,
            },
        }
        events.append(StartAuditEvent("START_HANDOFF_PREPARED", decision.identity, time()))
        try:
            port_result = self.port.submit(
                decision.plan,
                trace_id=decision.identity.trace_id,
                mode=self.mode,
                execution_metadata=metadata,
            )
        except (TypeError, ValueError) as exc:
            events.append(StartAuditEvent("START_HANDOFF_REJECTED", decision.identity, time()))
            return StartOrchestrationResult(
                False,
                decision.identity,
                f"handoff_rejected:{exc}",
                decision,
                audit=tuple(events),
            )
        events.append(
            StartAuditEvent(
                "START_HANDOFF_ACCEPTED" if port_result.accepted else "START_HANDOFF_REJECTED",
                decision.identity,
                time(),
            )
        )
        return StartOrchestrationResult(
            port_result.accepted,
            decision.identity,
            port_result.reason,
            decision,
            port_result,
            tuple(events),
        )
