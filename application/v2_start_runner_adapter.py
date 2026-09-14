"""Adapter to the preserved async V2 START transaction owner."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from .v2_start_transaction_adapter import V2StartTransactionInput


V2StartOwner = Callable[[Any, Any, Any], Awaitable[bool]]


@dataclass(frozen=True)
class V2StartRunnerAdapter:
    """Adapt V3 transaction data to ``start_profile_transactional`` only."""

    app: Any
    event_factory: Callable[[V2StartTransactionInput], Any]
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
        event = self.event_factory(transaction)
        started = await owner(self.app, event, pending)
        from .v2_start_transaction_adapter import V2TransactionOutcome

        return V2TransactionOutcome(
            trace_id=transaction.trace_id,
            started=bool(started),
            reason="started" if started else "v2_transaction_denied_or_failed",
        )
