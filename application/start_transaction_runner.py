"""Application runner for a prepared START transaction."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from .start_transaction_service import start_profile_transactional_result
from .start_event_context import StartEventContext
from .start_transaction_adapter import StartTransactionInput, StartTransactionOutcome


StartTransactionOwner = Callable[[Any, Any, Any], Awaitable[StartTransactionOutcome]]


class _ProductionMessage:
    """Minimal operator-event surface for non-Telegram production handoff."""

    def __init__(self, chat_id: str) -> None:
        self.chat = SimpleNamespace(id=int(chat_id) if str(chat_id).isdigit() else 0)
        self.last_answer: str | None = None

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        # The transaction owner already owns operator feedback. Capture its
        # existing response so the outer production route can deliver it once.
        # Do not send here: the callback route sends the normalized result.
        if args and isinstance(args[0], str):
            self.last_answer = args[0]
        return None


def build_start_event_context(transaction: StartTransactionInput) -> StartEventContext:
    return StartEventContext(
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
    event_factory: Callable[[StartTransactionInput], Any] | None = None
    transaction_owner: StartTransactionOwner | None = None

    async def __call__(self, transaction: StartTransactionInput) -> StartTransactionOutcome:
        pending = SimpleNamespace(
            profile=transaction.profile,
            capacity_ah=transaction.capacity_ah,
            intent=transaction.intent,
            battery_id=transaction.battery_id,
            condition=transaction.condition,
            recipe_id=transaction.intent_metadata.get("user_recipe_id"),
            recipe_version=transaction.intent_metadata.get("user_recipe_version"),
            native_recipe_name=transaction.intent_metadata.get("native_recipe_name"),
            native_recipe_version=transaction.intent_metadata.get("native_recipe_version"),
        )
        event = (self.event_factory or build_start_event_context)(transaction)
        if self.event_factory is None or isinstance(event, StartEventContext):
            message = _ProductionMessage(transaction.actor)
            event = SimpleNamespace(
                message=message,
                from_user=SimpleNamespace(id=message.chat.id),
                context=event,
            )
        owner = self.transaction_owner or start_profile_transactional_result
        outcome = await owner(self.app, event, pending)
        if not isinstance(outcome, StartTransactionOutcome):
            raise TypeError("START transaction owner must return StartTransactionOutcome")
        message = getattr(event, "message", None)
        reason = (outcome.reason or "started") if outcome.started else (
            getattr(message, "last_answer", None) or outcome.reason
            or "start_transaction_denied_or_failed"
        )
        return StartTransactionOutcome(
            trace_id=outcome.trace_id or transaction.trace_id, started=outcome.started,
            denied=outcome.denied, contained=outcome.contained,
            output_off_confirmed=outcome.output_off_confirmed,
            output_off_unconfirmed=outcome.output_off_unconfirmed,
            session_cleared=outcome.session_cleared,
            session_contained=outcome.session_contained, reason=reason,
            persistence_status=outcome.persistence_status,
        )


__all__ = [
    "StartTransactionOwner",
    "StartTransactionRunner",
    "build_start_event_context",
]
