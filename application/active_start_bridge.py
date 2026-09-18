"""Explicitly gated ACTIVE bridge composition for the preserved V2 owner."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from .operator_feedback import OperatorFeedbackPort, build_legacy_feedback_bridge
from .production_start_runner import ProductionStartRunner
from .start_activation_policy import StartActivationPolicy
from .start_execution_contract import StartExecutionRequest
from .v2_start_event_context import V2StartEventContext
from .v2_start_transaction_adapter import (
    StartExecutionResult,
    V2StartOwner,
    V2StartTransactionAdapter,
    V2StartTransactionExecutor,
    build_v2_start_event_context,
)


@dataclass(frozen=True)
class LegacyOperatorEventFacade:
    """Small legacy-compatible facade; it contains no V3/runtime handles."""

    message: Any
    from_user: Any


class ActiveStartExecutionBridge:
    """Compose feedback and the gated runner without owning START decisions."""

    def __init__(
        self,
        app: Any,
        *,
        activation_policy: StartActivationPolicy | None = None,
        transaction_adapter: V2StartTransactionAdapter | None = None,
        transaction_owner: V2StartOwner | None = None,
    ) -> None:
        self.app = app
        self.activation_policy = activation_policy or StartActivationPolicy()
        self.transaction_adapter = transaction_adapter or V2StartTransactionAdapter()
        self.transaction_owner = transaction_owner

    async def execute(
        self,
        request: StartExecutionRequest,
        feedback_port: OperatorFeedbackPort,
    ) -> StartExecutionResult:
        def event_factory(transaction):
            context: V2StartEventContext = build_v2_start_event_context(transaction)
            feedback = build_legacy_feedback_bridge(context, feedback_port)
            user = SimpleNamespace(id=context.actor)
            return LegacyOperatorEventFacade(message=feedback, from_user=user)

        runner_adapter = V2StartTransactionExecutor(
            self.app,
            event_factory=event_factory,
            transaction_owner=self.transaction_owner,
        )
        runner = ProductionStartRunner(
            transaction_adapter=self.transaction_adapter,
            activation_policy=self.activation_policy,
            transaction_runner=runner_adapter,
        )
        return await runner.execute_async(request)
