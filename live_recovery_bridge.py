from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from battery_registry import RecoveryCycleEvidence
from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision
from recovery_runtime import RecoveryRuntime, RecoveryRuntimeObservation

logger = logging.getLogger("rd6018.recovery")


@dataclass(frozen=True)
class LiveRecoveryObservation:
    decision: str
    reason: str
    legacy_effect: str
    disagreement: Optional[str]
    evidence: RecoveryCycleEvidence

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "legacy_effect": self.legacy_effect,
            "disagreement": self.disagreement,
            "battery_id": self.evidence.battery_id,
            "main_imin_a": self.evidence.main_imin_a,
            "hv_imin_a": self.evidence.hv_imin_a,
            "hv_reversal_delta_a": self.evidence.hv_reversal_delta_a,
            "temp_max_c": self.evidence.temp_max_c,
            "max_dtemp_c_per_min": self.evidence.max_dtemp_c_per_min,
        }


class LiveRecoveryBridge:
    """Persistent production shadow bridge for legacy FSM telemetry.

    This class is intentionally non-actuating: it has no HassClient and never mutates
    the legacy actions mapping. It owns exactly one RecoveryRuntime so persistence and
    policy decisions are derived from the same evidence stream.
    """

    def __init__(self, runtime: Optional[RecoveryRuntime] = None) -> None:
        self.runtime = runtime or RecoveryRuntime()
        self._decision_counts: Counter[str] = Counter()
        self._disagreement_counts: Counter[str] = Counter()
        self._samples = 0

    @property
    def active(self) -> bool:
        return self.runtime.active

    async def start(
        self,
        *,
        battery_id: str,
        started_at: float,
        intent: ChargeIntent,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
    ) -> None:
        await self.runtime.start(
            battery_id=battery_id,
            started_at=started_at,
            intent=intent,
            condition_before=condition_before,
        )
        self._decision_counts.clear()
        self._disagreement_counts.clear()
        self._samples = 0

    @staticmethod
    def _legacy_effect(actions: Optional[Mapping[str, Any]]) -> str:
        if not actions:
            return "continue"
        if actions.get("emergency_stop"):
            return "emergency_stop"
        if actions.get("turn_off"):
            return "turn_off"
        if actions.get("turn_on"):
            return "turn_on"
        if actions.get("set_voltage") is not None or actions.get("set_current") is not None:
            return "retarget"
        return "continue"

    @staticmethod
    def _disagreement(decision: RecoveryDecision, legacy_effect: str) -> Optional[str]:
        if decision == RecoveryDecision.HOLD_OUTPUT_OFF and legacy_effect not in {
            "turn_off",
            "emergency_stop",
        }:
            return "v2_requires_output_off"
        if decision == RecoveryDecision.PAUSE_THERMAL and legacy_effect not in {
            "turn_off",
            "emergency_stop",
        }:
            return "v2_requires_thermal_pause"
        if decision == RecoveryDecision.REST_AND_DIAGNOSE and legacy_effect not in {
            "turn_off",
            "emergency_stop",
        }:
            return "v2_requires_rest"
        if decision == RecoveryDecision.FINISH_STAGE and legacy_effect in {
            "continue",
            "retarget",
            "turn_on",
        }:
            return "v2_would_finish_stage"
        return None

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
        legacy_actions: Optional[Mapping[str, Any]] = None,
    ) -> LiveRecoveryObservation:
        observation: RecoveryRuntimeObservation = self.runtime.observe(
            timestamp_s=timestamp_s,
            stage=stage,
            voltage_v=voltage_v,
            current_a=current_a,
            temp_c=temp_c,
            is_cv=is_cv,
            target_voltage_v=target_voltage_v,
            ah=ah,
            output_is_on=output_is_on,
        )
        legacy_effect = self._legacy_effect(legacy_actions)
        disagreement = self._disagreement(
            observation.decision.decision,
            legacy_effect,
        )
        result = LiveRecoveryObservation(
            decision=observation.decision.decision.value,
            reason=observation.decision.reason,
            legacy_effect=legacy_effect,
            disagreement=disagreement,
            evidence=observation.evidence,
        )
        self._samples += 1
        self._decision_counts[result.decision] += 1
        if disagreement is not None:
            self._disagreement_counts[disagreement] += 1
            logger.warning(
                "RECOVERY_SHADOW disagreement=%s decision=%s legacy=%s stage=%s "
                "battery_id=%s reason=%s",
                disagreement,
                result.decision,
                legacy_effect,
                stage,
                result.evidence.battery_id,
                result.reason,
            )
        return result

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
        return await self.runtime.complete(
            completed_at=completed_at,
            outcome=outcome,
            measured_capacity_ah=measured_capacity_ah,
            cca_a=cca_a,
            internal_resistance_mohm=internal_resistance_mohm,
            notes=notes,
        )

    def abort(self) -> None:
        self.runtime.abort()

    def summary(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "samples": self._samples,
            "decision_counts": dict(sorted(self._decision_counts.items())),
            "disagreement_counts": dict(sorted(self._disagreement_counts.items())),
            "battery_id": self.runtime.battery_id,
            "evidence": self.runtime.evidence,
        }
