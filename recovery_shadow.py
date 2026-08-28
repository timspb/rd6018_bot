from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision, RecoveryDecisionPolicy, RecoveryDecisionResult
from recovery_session import RecoverySessionTracker, RecoveryTracePoint
from signal_analyzer import SignalAnalysis


@dataclass(frozen=True)
class ShadowRecoveryRecord:
    point: RecoveryTracePoint
    analysis: SignalAnalysis
    decision: RecoveryDecisionResult
    legacy_effect: str
    disagreement: Optional[str]


class ShadowRecoveryRuntime:
    """Run the V2 evidence/policy stack beside the legacy FSM without actuating it.

    The runtime intentionally has no HassClient reference and cannot switch the
    RD6018 output. It is suitable for production shadow observation before the
    legacy FSM is migrated to evidence-driven transitions.
    """

    def __init__(
        self,
        *,
        battery_id: str,
        started_at: float,
        intent: ChargeIntent = ChargeIntent.RECOVERY,
        condition_before: BatteryCondition = BatteryCondition.UNKNOWN,
    ) -> None:
        self.intent = intent
        self.tracker = RecoverySessionTracker(
            battery_id=battery_id,
            started_at=started_at,
            intent=intent,
            condition_before=condition_before,
        )
        self.policy = RecoveryDecisionPolicy()
        self.records: list[ShadowRecoveryRecord] = []

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
        point: RecoveryTracePoint,
        *,
        legacy_actions: Optional[Mapping[str, Any]] = None,
        output_is_on: Optional[bool] = True,
    ) -> ShadowRecoveryRecord:
        analysis = self.tracker.observe(point)
        decision = self.policy.decide(
            analysis,
            stage=point.stage,
            intent=self.intent,
            output_is_on=output_is_on,
        )
        legacy_effect = self._legacy_effect(legacy_actions)
        record = ShadowRecoveryRecord(
            point=point,
            analysis=analysis,
            decision=decision,
            legacy_effect=legacy_effect,
            disagreement=self._disagreement(decision.decision, legacy_effect),
        )
        self.records.append(record)
        return record

    def summary(self) -> dict[str, Any]:
        decisions = Counter(record.decision.decision.value for record in self.records)
        disagreements = Counter(
            record.disagreement for record in self.records if record.disagreement is not None
        )
        return {
            "samples": len(self.records),
            "decision_counts": dict(sorted(decisions.items())),
            "disagreement_counts": dict(sorted(disagreements.items())),
            "evidence": self.tracker.evidence,
        }
