"""Application runner for a prepared START transaction."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from .start_transaction_service import start_profile_transactional
from .start_event_context import V2StartEventContext
from .start_transaction_adapter import V2StartTransactionInput, V2TransactionOutcome


StartTransactionOwner = Callable[[Any, Any, Any], Awaitable[bool]]


class _ProductionMessage:
    """Minimal operator-event surface for non-Telegram production handoff."""

    def __init__(self, chat_id: str) -> None:
        self.chat = SimpleNamespace(id=int(chat_id) if str(chat_id).isdigit() else 0)

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        return None


def build_start_event_context(transaction: V2StartTransactionInput) -> V2StartEventContext:
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
class StartTransactionRunner:
    """Adapt prepared START transaction data to the application-owned owner."""

    app: Any
    event_factory: Callable[[V2StartTransactionInput], Any] | None = None
    transaction_owner: StartTransactionOwner | None = None

    async def __call__(self, transaction: V2StartTransactionInput) -> V2TransactionOutcome:
        pending = SimpleNamespace(
            profile=transaction.profile,
            capacity_ah=transaction.capacity_ah,
            intent=transaction.intent,
            battery_id=transaction.battery_id,
            condition=transaction.condition,
        )
        event = (self.event_factory or build_start_event_context)(transaction)
        if self.event_factory is None or isinstance(event, V2StartEventContext):
            message = _ProductionMessage(transaction.actor)
            event = SimpleNamespace(
                message=message,
                from_user=SimpleNamespace(id=message.chat.id),
                context=event,
            )
        owner = self.transaction_owner or start_profile_transactional
        started = await owner(self.app, event, pending)
        return V2TransactionOutcome(
            trace_id=transaction.trace_id,
            started=bool(started),
            reason="started" if started else "start_transaction_denied_or_failed",
        )


__all__ = [
    "StartTransactionOwner",
    "StartTransactionRunner",
    "build_start_event_context",
]
