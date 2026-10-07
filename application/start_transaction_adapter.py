"""Data-only adapter contract for the preserved V2 START transaction owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping

from pb_domain import BatteryCondition, ChargeIntent

from .start_plan import ApprovedStartPlan


class StartExecutionStatus(str, Enum):
    STARTED = "STARTED"
    FAILED = "FAILED"
    DENIED = "DENIED"
    CONTAINED = "CONTAINED"


class RollbackState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    OFF_CONFIRMED = "OFF_CONFIRMED"
    OFF_UNCONFIRMED = "OFF_UNCONFIRMED"
    SESSION_CLEARED = "SESSION_CLEARED"
    SESSION_CONTAINED = "SESSION_CONTAINED"


@dataclass(frozen=True)
class V2StartTransactionInput:
    trace_id: str
    profile: str
    chemistry: str
    capacity_ah: float
    battery_id: str
    recipe_id: str
    target_voltage_v: float
    target_current_a: float
    ownership_decision: str
    safety_decision: str
    intent: ChargeIntent = ChargeIntent.NORMAL
    condition: BatteryCondition = BatteryCondition.UNKNOWN
    actor: str = ""
    source: str = ""
    intent_metadata: Mapping[str, Any] = field(default_factory=dict)
    correlation_metadata: Mapping[str, Any] = field(default_factory=dict)
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_metadata", MappingProxyType(dict(self.intent_metadata)))
        object.__setattr__(self, "correlation_metadata", MappingProxyType(dict(self.correlation_metadata)))


@dataclass(frozen=True)
class V2TransactionOutcome:
    trace_id: str = ""
    started: bool = False
    denied: bool = False
    contained: bool = False
    output_off_confirmed: bool = False
    output_off_unconfirmed: bool = False
    session_cleared: bool = False
    session_contained: bool = False
    reason: str = ""


@dataclass(frozen=True)
class StartExecutionResult:
    trace_id: str
    status: StartExecutionStatus
    rollback: RollbackState
    reason: str
    transaction_input: V2StartTransactionInput
    session_id: str | None = None


class V2StartTransactionAdapter:
    """Translate a V3 plan to V2 data without owning V2 execution."""

    def prepare(
        self,
        plan: ApprovedStartPlan,
        *,
        trace_id: str = "unbound",
        intent: ChargeIntent = ChargeIntent.NORMAL,
        condition: BatteryCondition = BatteryCondition.UNKNOWN,
        execution_metadata: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> V2StartTransactionInput:
        if plan.ownership_result != "available":
            raise ValueError("cannot prepare V2 transaction without ownership")
        if plan.safety_result != "allowed":
            raise ValueError("cannot prepare V2 transaction without safety approval")
        metadata = dict(execution_metadata or {})
        correlation_metadata = dict(metadata.get("correlation_metadata") or {})
        correlation_metadata.setdefault("trace_id", trace_id)
        effective_session_id = session_id or metadata.get("session_id")
        if effective_session_id:
            correlation_metadata.setdefault("session_id", str(effective_session_id))
        intent_metadata = dict(metadata.get("intent_metadata") or {})
        intent_metadata.setdefault("intent", intent.value)
        intent_metadata.setdefault("condition", condition.value)
        return V2StartTransactionInput(
            trace_id=trace_id,
            profile=plan.profile,
            chemistry=plan.chemistry,
            capacity_ah=float(plan.battery_identity.nominal_capacity_ah),
            battery_id=plan.battery_identity.battery_id,
            recipe_id=plan.recipe_id,
            target_voltage_v=plan.target_preview.voltage_v,
            target_current_a=plan.target_preview.current_a,
            ownership_decision=plan.ownership_result,
            safety_decision=plan.safety_result,
            intent=intent,
            condition=condition,
            actor=str(metadata.get("operator") or metadata.get("user") or ""),
            source=str(metadata.get("source") or ""),
            intent_metadata=intent_metadata,
            correlation_metadata=correlation_metadata,
            session_id=str(effective_session_id) if effective_session_id else None,
        )

    def normalize(
        self,
        plan: ApprovedStartPlan,
        outcome: V2TransactionOutcome,
        *,
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> StartExecutionResult:
        correlation_id = trace_id or outcome.trace_id or "unbound"
        transaction_input = self.prepare(
            plan,
            trace_id=correlation_id,
            execution_metadata={"session_id": session_id} if session_id else None,
        )
        if outcome.contained or outcome.session_contained:
            status = StartExecutionStatus.CONTAINED
        elif outcome.denied:
            status = StartExecutionStatus.DENIED
        elif outcome.started:
            status = StartExecutionStatus.STARTED
        else:
            status = StartExecutionStatus.FAILED

        if outcome.session_contained:
            rollback = RollbackState.SESSION_CONTAINED
        elif outcome.output_off_unconfirmed:
            rollback = RollbackState.OFF_UNCONFIRMED
        elif outcome.session_cleared:
            rollback = RollbackState.SESSION_CLEARED
        elif outcome.output_off_confirmed:
            rollback = RollbackState.OFF_CONFIRMED
        else:
            rollback = RollbackState.NOT_REQUIRED if status is StartExecutionStatus.STARTED else RollbackState.NOT_REQUIRED

        return StartExecutionResult(
            correlation_id,
            status,
            rollback,
            outcome.reason or status.value,
            transaction_input,
            session_id=session_id or transaction_input.session_id,
        )

    def execute(
        self,
        plan: ApprovedStartPlan,
        transaction_runner: Callable[[V2StartTransactionInput], Any] | None = None,
        *,
        active_enabled: bool = False,
    ) -> StartExecutionResult:
        """ACTIVE-off guard; the preserved V2 owner is not invoked by default."""
        transaction_input = self.prepare(plan)
        if not active_enabled:
            return StartExecutionResult(
                "unbound",
                StartExecutionStatus.DENIED,
                RollbackState.NOT_REQUIRED,
                "active_execution_disabled",
                transaction_input,
            )
        if transaction_runner is None:
            return StartExecutionResult(
                "unbound",
                StartExecutionStatus.DENIED,
                RollbackState.NOT_REQUIRED,
                "v2_transaction_runner_not_configured",
                transaction_input,
            )
        raise RuntimeError("ACTIVE V2 START transaction requires separate production approval")
