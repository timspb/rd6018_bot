"""Non-actuating production Telegram START route through the V3 boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from .intents import OperatorIntent, OperatorIntentKind
from .production_start_execution_port import (
    ProductionStartExecutionPort,
    ProductionStartMode,
    ProductionStartPortResult,
)
from .start_plan import ApprovedStartPlan, approved_plan_from_preflight
from .start_preflight import StartPreflightService
from .start_request import StartIntentValidator, StartRequest


@dataclass(frozen=True)
class ProductionStartRouteResult:
    accepted: bool
    trace_id: str
    reason: str
    port_result: ProductionStartPortResult | None = None
    plan: ApprovedStartPlan | None = None


class ProductionStartRouteAdapter:
    """Convert one Telegram START intent into a gated, read-only V3 route."""

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
        self.preflight = StartPreflightService(app)
        self.port = port or ProductionStartExecutionPort()

    async def submit(self, intent: OperatorIntent) -> ProductionStartRouteResult:
        trace_id = uuid4().hex
        if intent.kind is not OperatorIntentKind.START_CHARGE:
            return ProductionStartRouteResult(False, trace_id, "invalid_start_intent")

        if not StartIntentValidator.validate(intent.parameters):
            return ProductionStartRouteResult(False, trace_id, "invalid_start_intent")

        try:
            request = self._request_from_intent(intent)
            preflight = await self.preflight.evaluate(request)
        except (TypeError, ValueError, KeyError) as exc:
            return ProductionStartRouteResult(False, trace_id, f"invalid_start_request:{exc}")

        if not preflight.allowed:
            return ProductionStartRouteResult(
                False,
                trace_id,
                "preflight_denied:" + ",".join(preflight.reasons),
            )

        try:
            plan = approved_plan_from_preflight(preflight)
            port_result = self.port.submit(
                plan,
                trace_id=trace_id,
                mode=self.mode,
                execution_metadata={
                    "source": intent.source,
                    "operator": intent.user,
                    "intent": request.intent,
                    "condition": request.condition,
                },
            )
        except (TypeError, ValueError) as exc:
            return ProductionStartRouteResult(False, trace_id, f"route_rejected:{exc}")

        return ProductionStartRouteResult(
            port_result.accepted,
            trace_id,
            port_result.reason,
            port_result,
            plan,
        )

    @staticmethod
    def _request_from_intent(intent: OperatorIntent) -> StartRequest:
        values: Mapping[str, Any] = intent.parameters
        return StartRequest(
            profile=str(values["profile"]),
            capacity_ah=float(values["capacity_ah"]),
            battery_identity=values.get("battery_identity"),
            battery_id=str(values.get("battery_id", "operator-battery")),
            intent=values["intent"],
            condition=values["condition"],
            operator=intent.user,
            context={"source": intent.source},
        )
