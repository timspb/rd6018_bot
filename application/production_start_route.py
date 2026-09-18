"""Non-actuating production Telegram START route through the V3 boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intents import OperatorIntent, OperatorIntentKind
from .production_start_execution_port import (
    ProductionStartExecutionPort,
    ProductionStartMode,
    ProductionStartPortResult,
)
from .start_authority import StartAuthority
from .start_orchestration import StartOrchestration


@dataclass(frozen=True)
class ProductionStartRouteResult:
    accepted: bool
    trace_id: str
    reason: str
    port_result: ProductionStartPortResult | None = None
    plan: ApprovedStartPlan | None = None


class ProductionStartRouteAdapter:
    """Transport adapter over the canonical START authority/orchestration."""

    def __init__(
        self,
        app: Any,
        *,
        mode: ProductionStartMode = ProductionStartMode.DRY_RUN,
        port: ProductionStartExecutionPort | None = None,
    ) -> None:
        if mode is ProductionStartMode.ACTIVE:
            raise ValueError("production Telegram START ACTIVE mode is disabled")
        self.app = app
        self.mode = mode
        self.port = port or ProductionStartExecutionPort()
        self.authority = StartAuthority(app)
        self.orchestration = StartOrchestration(self.authority, self.port, mode=mode)
        self.preflight = self.authority.preflight

    async def submit(self, intent: OperatorIntent) -> ProductionStartRouteResult:
        result = await self.orchestration.submit(intent)
        port_result = result.port_result
        if port_result is None:
            return ProductionStartRouteResult(
                False,
                result.identity.trace_id,
                result.reason,
                None,
                result.authority.plan,
            )
        return ProductionStartRouteResult(
            port_result.accepted,
            result.identity.trace_id,
            port_result.reason,
            port_result,
            result.authority.plan,
        )
