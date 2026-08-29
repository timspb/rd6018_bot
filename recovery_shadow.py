from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision, RecoveryDecisionPolicy, RecoveryDecisionResult
from recovery_session import RecoverySessionTracker, RecoveryTracePoint
from signal_analyzer import SignalAnalysis, SignalMetrics, SignalSample


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

    @staticmethod
    def _neutral_analysis(point: RecoveryTracePoint) -> SignalAnalysis:
        """Represent an intentional output-OFF charge sample without mutating evidence.

        During transactional startup the controller can already own Main/Mix while the
        RD6018 output is still OFF.  Feeding that arming sample into SignalAnalyzer can
        manufacture a 0 A Imin (or an irrelevant CC Vmax) whose age later influences
        transition timing.  Keep the point auditable, but leave the charge trajectory
        untouched until output is actually energized.
        """
        return SignalAnalysis(
            sample=SignalSample(
                timestamp_s=float(point.timestamp_s),
                voltage_v=float(point.voltage_v),
                current_a=float(point.current_a),
                temp_c=float(point.temp_c),
                is_cv=bool(point.is_cv),
                is_cc=bool(point.is_cc),
            ),
            metrics=SignalMetrics(
                d_voltage_v_per_min=None,
                d_current_a_per_min=None,
                d_temp_c_per_min=None,
                current_min_a=None,
                seconds_since_current_min=None,
                delta_current_from_min_a=None,
                reversal_threshold_a=None,
                current_plateau_span_a=None,
                current_plateau_center_a=None,
                reversal_confirmations=0,
                voltage_max_v=None,
                seconds_since_voltage_max=None,
                delta_voltage_from_max_v=None,
                voltage_reversal_threshold_v=None,
                voltage_reversal_confirmations=0,
            ),
            events=frozenset(),
        )

    def observe(
        self,
        point: RecoveryTracePoint,
        *,
        legacy_actions: Optional[Mapping[str, Any]] = None,
        output_is_on: Optional[bool] = True,
    ) -> ShadowRecoveryRecord:
        stage_kind = self.tracker._stage_kind(point.stage)
        if output_is_on is False and stage_kind in {"main", "hv"}:
            # Do not let OFF/arming/cooling samples seed Imin/Vmax or their clocks.
            # Relaxation stages intentionally remain observable with output OFF.
            analysis = self._neutral_analysis(point)
        else:
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
