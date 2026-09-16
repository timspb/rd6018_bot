"""Gated handoff from the V3 START contract to the preserved V2 owner."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Callable

from pb_domain import BatteryCondition, ChargeIntent

from .start_activation_policy import StartActivationPolicy, StartExecutionMode
from .start_execution_contract import StartExecutionRequest
from .v2_start_transaction_adapter import (
    RollbackState,
    StartExecutionResult,
    StartExecutionStatus,
    V2StartTransactionAdapter,
    V2TransactionOutcome,
)


V2TransactionRunner = Callable[[object], V2TransactionOutcome]


@dataclass(frozen=True)
class ProductionStartRunner:
    """Invoke only an injected V2 transaction owner after all ACTIVE gates pass."""

    transaction_adapter: V2StartTransactionAdapter
    activation_policy: StartActivationPolicy
    transaction_runner: V2TransactionRunner

    def execute(self, request: StartExecutionRequest) -> StartExecutionResult:
        decision = self.activation_policy.evaluate(StartExecutionMode.ACTIVE)
        if not decision.allowed:
            return self._denied(request, ",".join(decision.reasons))

        transaction_input = self._prepare(request)
        try:
            outcome = self.transaction_runner(transaction_input)
        except Exception as exc:  # runner failures are normalized, not leaked
            outcome = V2TransactionOutcome(
                trace_id=request.trace_id,
                reason=f"runner_failed:{type(exc).__name__}",
            )
        if not isinstance(outcome, V2TransactionOutcome):
            outcome = V2TransactionOutcome(
                trace_id=request.trace_id,
                reason="runner_returned_invalid_outcome",
            )
        return self.transaction_adapter.normalize(
            request.plan,
            outcome,
            trace_id=request.trace_id,
        )

    async def execute_async(self, request: StartExecutionRequest) -> StartExecutionResult:
        """Async variant for the existing async V2 transaction owner."""
        decision = self.activation_policy.evaluate(StartExecutionMode.ACTIVE)
        if not decision.allowed:
            return self._denied(request, ",".join(decision.reasons))

        transaction_input = self._prepare(request)
        try:
            outcome = self.transaction_runner(transaction_input)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        except Exception as exc:  # runner failures are normalized, not leaked
            outcome = V2TransactionOutcome(
                trace_id=request.trace_id,
                reason=f"runner_failed:{type(exc).__name__}",
            )
        if not isinstance(outcome, V2TransactionOutcome):
            outcome = V2TransactionOutcome(
                trace_id=request.trace_id,
                reason="runner_returned_invalid_outcome",
            )
        return self.transaction_adapter.normalize(
            request.plan,
            outcome,
            trace_id=request.trace_id,
        )

    def _prepare(self, request: StartExecutionRequest):
        return self.transaction_adapter.prepare(
            request.plan,
            trace_id=request.trace_id,
            intent=request.execution_metadata.get("intent") or ChargeIntent.NORMAL,
            condition=request.execution_metadata.get("condition") or BatteryCondition.UNKNOWN,
            execution_metadata=request.execution_metadata,
        )

    def _denied(self, request: StartExecutionRequest, reason: str) -> StartExecutionResult:
        transaction_input = self.transaction_adapter.prepare(
            request.plan,
            trace_id=request.trace_id,
            intent=request.execution_metadata.get("intent") or ChargeIntent.NORMAL,
            condition=request.execution_metadata.get("condition") or BatteryCondition.UNKNOWN,
            execution_metadata=request.execution_metadata,
        )
        return StartExecutionResult(
            trace_id=request.trace_id,
            status=StartExecutionStatus.DENIED,
            rollback=RollbackState.NOT_REQUIRED,
            reason=reason or "active_execution_disabled",
            transaction_input=transaction_input,
        )
