"""Canonical lifecycle admission for START requests."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any, Mapping
from uuid import uuid4

from .intents import OperatorIntent, OperatorIntentKind
from .start_plan import ApprovedStartPlan, approved_plan_from_preflight
from .start_preflight import StartPreflightService
from .start_request import StartIntentValidator, StartRequest


@dataclass(frozen=True)
class StartIdentity:
    request_id: str
    trace_id: str
    session_id: str | None = None
    created_at: float = 0.0


@dataclass(frozen=True)
class StartAuthorityDecision:
    accepted: bool
    identity: StartIdentity
    reason: str
    plan: ApprovedStartPlan | None = None


class StartAuthority:
    """Single START admission owner; it never performs physical execution."""

    def __init__(self, app: Any, *, preflight: StartPreflightService | None = None) -> None:
        self.preflight = preflight or StartPreflightService(app)

    async def authorize(self, intent: OperatorIntent) -> StartAuthorityDecision:
        created_at = time()
        identity = StartIdentity(
            request_id=uuid4().hex,
            trace_id=uuid4().hex,
            created_at=created_at,
        )
        if intent.kind is not OperatorIntentKind.START_CHARGE:
            return StartAuthorityDecision(False, identity, "invalid_start_intent")
        if not StartIntentValidator.validate(intent.parameters):
            return StartAuthorityDecision(False, identity, "invalid_start_intent")
        try:
            request = self.request_from_intent(intent)
            preflight = await self.preflight.evaluate(request)
        except (TypeError, ValueError, KeyError) as exc:
            return StartAuthorityDecision(False, identity, f"invalid_start_request:{exc}")
        if not preflight.allowed:
            return StartAuthorityDecision(
                False,
                identity,
                "preflight_denied:" + ",".join(preflight.reasons),
            )
        try:
            plan = approved_plan_from_preflight(preflight)
        except (TypeError, ValueError) as exc:
            return StartAuthorityDecision(False, identity, f"plan_rejected:{exc}")
        accepted_identity = StartIdentity(
            request_id=identity.request_id,
            trace_id=identity.trace_id,
            session_id=uuid4().hex,
            created_at=created_at,
        )
        return StartAuthorityDecision(True, accepted_identity, "start_authorized", plan)

    @staticmethod
    def request_from_intent(intent: OperatorIntent) -> StartRequest:
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
