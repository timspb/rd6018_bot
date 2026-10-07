"""Gated handoff from the V3 START contract to the preserved V2 owner."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Callable

from pb_domain import BatteryCondition, ChargeIntent

from .start_execution_contract import StartExecutionRequest
from .start_transaction_adapter import (
    RollbackState,
    StartExecutionResult,
    StartExecutionStatus,
    StartTransactionAdapter,
    StartTransactionOutcome,
)


StartTransactionCallable = Callable[[object], StartTransactionOutcome]


@dataclass(frozen=True)
class ProductionStartRunner:
    """Invoke the preserved V2 transaction owner after START preflight."""

    transaction_adapter: StartTransactionAdapter
    transaction_runner: StartTransactionCallable

    def execute(self, request: StartExecutionRequest) -> StartExecutionResult:
        transaction_input = self._prepare(request)
        try:
            outcome = self.transaction_runner(transaction_input)
            if inspect.isawaitable(outcome):
                # The synchronous API cannot execute an async owner.  Close a
                # returned coroutine without running it so this path remains
                # fail-closed and does not leak an un-awaited coroutine.
                close = getattr(outcome, "close", None)
                if close is not None:
                    close()
        except Exception as exc:  # runner failures are normalized, not leaked
            outcome = StartTransactionOutcome(
                trace_id=request.trace_id,
                reason=f"runner_failed:{type(exc).__name__}",
            )
        if not isinstance(outcome, StartTransactionOutcome):
            outcome = StartTransactionOutcome(
                trace_id=request.trace_id,
                reason="runner_returned_invalid_outcome",
            )
        return self.transaction_adapter.normalize(
            request.plan,
            outcome,
            trace_id=request.trace_id,
            session_id=request.session_id,
        )

    async def execute_async(self, request: StartExecutionRequest) -> StartExecutionResult:
        """Async variant for the existing async V2 transaction owner."""
        transaction_input = self._prepare(request)
        try:
            outcome = self.transaction_runner(transaction_input)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        except Exception as exc:  # runner failures are normalized, not leaked
            outcome = StartTransactionOutcome(
                trace_id=request.trace_id,
                reason=f"runner_failed:{type(exc).__name__}",
            )
        if not isinstance(outcome, StartTransactionOutcome):
            outcome = StartTransactionOutcome(
                trace_id=request.trace_id,
                reason="runner_returned_invalid_outcome",
            )
        return self.transaction_adapter.normalize(
            request.plan,
            outcome,
            trace_id=request.trace_id,
            session_id=request.session_id,
        )

    def _prepare(self, request: StartExecutionRequest):
        return self.transaction_adapter.prepare(
            request.plan,
            trace_id=request.trace_id,
            intent=request.execution_metadata.get("intent") or ChargeIntent.NORMAL,
            condition=request.execution_metadata.get("condition") or BatteryCondition.UNKNOWN,
            execution_metadata=request.execution_metadata,
            session_id=request.session_id,
        )
