"""Adapter to the preserved async V2 START transaction owner."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from .v2_start_transaction_adapter import V2StartTransactionInput
from .v2_start_event_context import V2StartEventContext


V2StartOwner = Callable[[Any, Any, Any], Awaitable[bool]]


class _ProductionMessage:
    """Minimal message surface for the preserved transaction owner."""

    def __init__(self, chat_id: str) -> None:
        self.chat = SimpleNamespace(id=int(chat_id) if str(chat_id).isdigit() else 0)

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        return None


def build_v2_start_event_context(transaction: V2StartTransactionInput) -> V2StartEventContext:
    """Build the data-only context from the already correlated transaction."""
    return V2StartEventContext(
        trace_id=transaction.trace_id,
        actor=transaction.actor,
        source=transaction.source,
        intent_metadata=transaction.intent_metadata,
        profile=transaction.profile,
        capacity_ah=transaction.capacity_ah,
        condition=transaction.condition,
        correlation_metadata=transaction.correlation_metadata,
    )


@dataclass(frozen=True)
class V2StartRunnerAdapter:
    """Adapt V3 transaction data to ``start_profile_transactional`` only."""

    app: Any
    event_factory: Callable[[V2StartTransactionInput], Any] | None = None
    transaction_owner: V2StartOwner | None = None

    async def __call__(self, transaction: V2StartTransactionInput):
        if self.transaction_owner is None:
            from v2_startup import start_profile_transactional

            owner = start_profile_transactional
        else:
            owner = self.transaction_owner
        pending = SimpleNamespace(
            profile=transaction.profile,
            capacity_ah=transaction.capacity_ah,
            intent=transaction.intent,
            battery_id=transaction.battery_id,
            condition=transaction.condition,
        )
        event = (self.event_factory or build_v2_start_event_context)(transaction)
        if self.transaction_owner is None:
            event = SimpleNamespace(
                message=_ProductionMessage(transaction.actor),
                from_user=SimpleNamespace(id=_ProductionMessage(transaction.actor).chat.id),
                context=event,
            )
        started = await owner(self.app, event, pending)
        from .v2_start_transaction_adapter import V2TransactionOutcome

        return V2TransactionOutcome(
            trace_id=transaction.trace_id,
            started=bool(started),
            reason="started" if started else "v2_transaction_denied_or_failed",
        )
