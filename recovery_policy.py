from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional

from pb_domain import ChargeIntent
from signal_analyzer import SignalAnalysis, SignalEvent


class RecoveryDecision(str, Enum):
    CONTINUE = "continue"
    FINISH_STAGE = "finish_stage"
    HOLD_OUTPUT_OFF = "hold_output_off"
    REST_AND_DIAGNOSE = "rest_and_diagnose"
    PAUSE_THERMAL = "pause_thermal"


@dataclass(frozen=True)
class RecoveryDecisionResult:
    decision: RecoveryDecision
    reason: str
    evidence: FrozenSet[SignalEvent]
    confidence: str = "deterministic"


class RecoveryDecisionPolicy:
    """Translate U/I/T evidence into conservative controller intent.

    This layer deliberately does not choose voltages, currents or chemistry recipes.
    It answers only what the controller should do with already-observed evidence.

    Practitioner-grounded invariant:
    - current reversal after a real Imin can be normal end-of-charge evidence;
    - the same reversal with temperature acceleration is not an EOC signal;
    - reversal accompanied by voltage sag is a reason to rest/diagnose, not to push harder;
    - a flat current plateau by itself is evidence, not an automatic escalation trigger.
    """

    HV_STAGE_NAMES = frozenset(
        {
            "mix",
            "mix mode",
            "desulfation",
            "десульфатация",
            "conditioning",
            "recovery",
        }
    )
    MAIN_STAGE_NAMES = frozenset({"main", "main charge", "bulk", "absorption"})

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        return " ".join(str(stage).strip().lower().replace("_", " ").split())

    def decide(
        self,
        analysis: SignalAnalysis,
        *,
        stage: str,
        intent: ChargeIntent = ChargeIntent.RECOVERY,
        output_is_on: Optional[bool] = True,
    ) -> RecoveryDecisionResult:
        events = analysis.events
        stage_key = self._normalize_stage(stage)

        if SignalEvent.TELEMETRY_INVALID in events:
            return RecoveryDecisionResult(
                RecoveryDecision.HOLD_OUTPUT_OFF,
                "telemetry_invalid",
                events,
            )

        if SignalEvent.THERMAL_ACCELERATION in events:
            return RecoveryDecisionResult(
                RecoveryDecision.PAUSE_THERMAL,
                "current_rise_with_temperature_acceleration",
                events,
            )

        if SignalEvent.VOLTAGE_SAG_DURING_REVERSAL in events:
            return RecoveryDecisionResult(
                RecoveryDecision.REST_AND_DIAGNOSE,
                "current_reversal_with_voltage_sag",
                events,
            )

        if stage_key in self.HV_STAGE_NAMES:
            if SignalEvent.END_OF_CHARGE_LIKELY in events:
                return RecoveryDecisionResult(
                    RecoveryDecision.FINISH_STAGE,
                    "confirmed_current_reversal_after_imin_with_stable_u_t",
                    events,
                )
            if SignalEvent.CURRENT_PLATEAU in events:
                return RecoveryDecisionResult(
                    RecoveryDecision.CONTINUE,
                    "hv_current_plateau_observe_for_imin_or_reversal",
                    events,
                )

        if stage_key in self.MAIN_STAGE_NAMES:
            if SignalEvent.CURRENT_PLATEAU in events:
                return RecoveryDecisionResult(
                    RecoveryDecision.CONTINUE,
                    "main_current_plateau_is_evidence_not_forced_escalation",
                    events,
                )

        if intent == ChargeIntent.NORMAL and stage_key in self.HV_STAGE_NAMES:
            # A normal-charge recipe should only be in a HV stage deliberately.
            # Policy remains non-destructive: it does not invent a transition here.
            return RecoveryDecisionResult(
                RecoveryDecision.CONTINUE,
                "normal_intent_hv_stage_requires_explicit_recipe_context",
                events,
            )

        if output_is_on is False:
            return RecoveryDecisionResult(
                RecoveryDecision.CONTINUE,
                "output_already_off",
                events,
            )

        return RecoveryDecisionResult(
            RecoveryDecision.CONTINUE,
            "no_terminal_recovery_evidence",
            events,
        )
