"""Resolve a production START into DRY_RUN or the gated ACTIVE handoff."""

from __future__ import annotations

from typing import Any, Mapping

from .production_start_execution_port import (
    ProductionStartExecutionPort,
    ProductionStartMode,
    ProductionStartPortResult,
)
from .start_activation_policy import StartExecutionMode
from .start_authority_provider import StartAuthorityProvider
from .start_plan import ApprovedStartPlan


class ProductionStartExecutionResolver:
    """Select execution mode from the current runtime-owned authority only."""

    def __init__(
        self,
        execution_port: ProductionStartExecutionPort,
        authority_provider: StartAuthorityProvider,
    ) -> None:
        self.execution_port = execution_port
        self.authority_provider = authority_provider

    async def resolve(
        self,
        plan: ApprovedStartPlan,
        *,
        trace_id: str,
        execution_metadata: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> ProductionStartPortResult:
        policy = self.authority_provider.current_policy()
        if policy.evaluate(StartExecutionMode.ACTIVE).allowed:
            return await self.execution_port.submit_active(
                plan,
                trace_id=trace_id,
                execution_metadata=execution_metadata,
                session_id=session_id,
            )
        return self.execution_port.submit(
            plan,
            trace_id=trace_id,
            mode=ProductionStartMode.DRY_RUN,
            execution_metadata=execution_metadata,
            session_id=session_id,
        )


__all__ = ["ProductionStartExecutionResolver"]
