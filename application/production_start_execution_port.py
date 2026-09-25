"""V3 START port to the preserved V2 transaction owner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .runtime_start_service import RuntimeStartService, StartExecutionTrace
from .production_start_runner import ProductionStartRunner
from .start_execution_contract import StartExecutionRequest, request_from_trace
from .start_plan import ApprovedStartPlan
from .v2_start_transaction_adapter import (
    StartExecutionResult,
    StartExecutionStatus,
    V2StartTransactionAdapter,
    V2TransactionOutcome,
)


class ProductionStartMode(str, Enum):
    SHADOW = "shadow"
    DRY_RUN = "dry_run"
    ACTIVE = "active"


@dataclass(frozen=True)
class ProductionStartPortResult:
    accepted: bool
    mode: ProductionStartMode
    trace_id: str
    reason: str
    trace: StartExecutionTrace | None = None
    request: StartExecutionRequest | None = None
    execution_result: StartExecutionResult | None = None
    session_id: str | None = None


class ProductionStartExecutionPort:
    """Route V3 data to the preserved V2 boundary without owning execution."""

    def __init__(
        self,
        runtime_start_service: RuntimeStartService | None = None,
        transaction_adapter: V2StartTransactionAdapter | None = None,
        production_runner: ProductionStartRunner | None = None,
    ) -> None:
        self.runtime_start_service = runtime_start_service or RuntimeStartService()
        self.transaction_adapter = transaction_adapter or V2StartTransactionAdapter()
        self.production_runner = production_runner

    def submit(
        self,
        plan: ApprovedStartPlan,
        *,
        trace_id: str,
        mode: ProductionStartMode = ProductionStartMode.SHADOW,
        execution_metadata: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> ProductionStartPortResult:
        trace = self.runtime_start_service.build_trace(plan)
        if not trace.allowed:
            return ProductionStartPortResult(False, mode, trace_id, ", ".join(trace.reasons), trace=trace)

        if mode is ProductionStartMode.ACTIVE:
            request = request_from_trace(
                plan,
                trace,
                trace_id=trace_id,
                execution_metadata=execution_metadata,
                session_id=session_id,
            )
            if self.production_runner is None:
                return ProductionStartPortResult(
                    False,
                    mode,
                    trace_id,
                    "active_runner_not_configured",
                    trace=trace,
                    request=request,
                )
            return ProductionStartPortResult(
                False,
                mode,
                trace_id,
                "active_requires_async_handoff",
                trace=trace,
                request=request,
            )

        request = request_from_trace(
            plan,
            trace,
            trace_id=trace_id,
            execution_metadata=execution_metadata,
            session_id=session_id,
        )
        if mode is ProductionStartMode.SHADOW:
            return ProductionStartPortResult(True, mode, trace_id, "shadow_trace_created", trace=trace, request=request)

        # DRY_RUN performs the complete data routing and adapter preparation,
        # but deliberately has no V2 transaction runner.
        self.transaction_adapter.prepare(plan, trace_id=trace_id)
        return ProductionStartPortResult(True, mode, trace_id, "dry_run_routed_no_mutation", trace=trace, request=request)

    def normalize_v2_outcome(
        self,
        request: StartExecutionRequest,
        outcome: V2TransactionOutcome,
    ) -> StartExecutionResult:
        """Normalize a captured V2 result while preserving request correlation."""
        return self.transaction_adapter.normalize(
            request.plan,
            outcome,
            trace_id=request.trace_id,
            session_id=request.session_id,
        )

    async def submit_active(
        self,
        plan: ApprovedStartPlan,
        *,
        trace_id: str,
        execution_metadata: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> ProductionStartPortResult:
        """Async ACTIVE boundary for the preserved async V2 transaction owner."""
        trace = self.runtime_start_service.build_trace(plan)
        if not trace.allowed:
            return ProductionStartPortResult(False, ProductionStartMode.ACTIVE, trace_id, ", ".join(trace.reasons), trace=trace)
        request = request_from_trace(
            plan,
            trace,
            trace_id=trace_id,
            execution_metadata=execution_metadata,
            session_id=session_id,
        )
        if self.production_runner is None:
            return ProductionStartPortResult(
                False,
                ProductionStartMode.ACTIVE,
                trace_id,
                "active_runner_not_configured",
                trace=trace,
                request=request,
            )
        result = await self.production_runner.execute_async(request)
        return ProductionStartPortResult(
            result.status is StartExecutionStatus.STARTED,
            ProductionStartMode.ACTIVE,
            trace_id,
            result.reason,
            trace=trace,
            request=request,
            execution_result=result,
            session_id=result.session_id,
        )
