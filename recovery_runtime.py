from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from battery_registry import RecoveryCycleEvidence, get_battery, record_recovery_cycle
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecisionPolicy, RecoveryDecisionResult
from recovery_session import RecoverySessionTracker, RecoveryTracePoint


BatteryExists = Callable[[str], Awaitable[bool]]
CyclePersister = Callable[[RecoveryCycleEvidence], Awaitable[int]]


async def _registry_battery_exists(battery_id: str) -> bool:
    return await get_battery(battery_id) is not None


@dataclass(frozen=True)
class RecoveryRuntimeObservation:
    decision: RecoveryDecisionResult
    evidence: RecoveryCycleEvidence


class RecoveryRuntime:
    """Own one active recovery session and bridge live telemetry to domain evidence.

    The runtime deliberately has no Telegram/HA dependencies. Production code feeds it
    the same validated U/I/T/stage data already used by the controller. It returns a
    conservative recovery-policy decision and persists exactly one completed evidence
    row when `complete()` is called.
    """

    def __init__(
        self,
        *,
        battery_exists: BatteryExists = _registry_battery_exists,
        persist_cycle: CyclePersister = record_recovery_cycle,
    ) -> None:
        self._battery_exists = battery_exists
        self._persist_cycle = persist_cycle
        self._tracker: Optional[RecoverySessionTracker] = None
        self._policy: Optional[RecoveryDecisionPolicy] = None
        self._battery_id: Optional[str] = None
        self._intent: ChargeIntent = ChargeIntent.RECOVERY
        self._condition_before: BatteryCondition = BatteryCondition.UNKNOWN

    @property
    def active(self) -> bool:
        return self._tracker is not None

    @property
    def battery_id(self) -> Optional[str]:
        return self._battery_id

    @property
    def evidence(self) -> Optional[RecoveryCycleEvidence]:
        return self._tracker.evidence if self._tracker is not None else None

    async def start(
        self,
        *,
        battery_id: str,
        started_at: float,
        intent: ChargeIntent,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
    ) -> None:
        battery_id = str(battery_id).strip()
        if not battery_id:
            raise ValueError("battery_id is required")
        if self.active:
            raise RuntimeError("recovery session already active")
        if not await self._battery_exists(battery_id):
            raise KeyError(f"unknown battery_id: {battery_id}")

        self._battery_id = battery_id
        self._intent = intent
        self._condition_before = condition_before
        self._tracker = RecoverySessionTracker(
            battery_id=battery_id,
            started_at=float(started_at),
            intent=intent,
            condition_before=condition_before,
        )
        self._policy = RecoveryDecisionPolicy()

    def observe(
        self,
        *,
        timestamp_s: float,
        stage: str,
        voltage_v: float,
        current_a: float,
        temp_c: float,
        is_cv: bool,
        target_voltage_v: Optional[float] = None,
        ah: Optional[float] = None,
        output_is_on: Optional[bool] = True,
    ) -> RecoveryRuntimeObservation:
        if self._tracker is None or self._policy is None:
            raise RuntimeError("no active recovery session")

        point = RecoveryTracePoint(
            timestamp_s=float(timestamp_s),
            stage=str(stage),
            voltage_v=float(voltage_v),
            current_a=float(current_a),
            temp_c=float(temp_c),
            is_cv=bool(is_cv),
            target_voltage_v=(
                float(target_voltage_v) if target_voltage_v is not None else None
            ),
            ah=float(ah) if ah is not None else None,
        )
        analysis = self._tracker.observe(point)
        decision = self._policy.decide(
            analysis,
            stage=point.stage,
            intent=self._intent,
            output_is_on=output_is_on,
        )
        return RecoveryRuntimeObservation(
            decision=decision,
            evidence=self._tracker.evidence,
        )

    async def complete(
        self,
        *,
        completed_at: float,
        outcome: str,
        measured_capacity_ah: Optional[float] = None,
        cca_a: Optional[float] = None,
        internal_resistance_mohm: Optional[float] = None,
        notes: str = "",
    ) -> RecoveryCycleEvidence:
        if self._tracker is None:
            raise RuntimeError("no active recovery session")

        evidence = self._tracker.complete(
            completed_at=float(completed_at),
            outcome=str(outcome),
            measured_capacity_ah=measured_capacity_ah,
            cca_a=cca_a,
            internal_resistance_mohm=internal_resistance_mohm,
            notes=str(notes),
        )
        await self._persist_cycle(evidence)
        self._reset()
        return evidence

    def abort(self) -> None:
        """Discard an unpersisted active session (for explicit operator cancellation)."""
        self._reset()

    def _reset(self) -> None:
        self._tracker = None
        self._policy = None
        self._battery_id = None
        self._intent = ChargeIntent.RECOVERY
        self._condition_before = BatteryCondition.UNKNOWN
