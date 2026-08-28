import unittest

from pb_domain import ChargeIntent
from recovery_policy import RecoveryDecision, RecoveryDecisionPolicy
from signal_analyzer import SignalAnalysis, SignalEvent, SignalMetrics, SignalSample


def analysis_with(*events: SignalEvent, is_cv: bool = True, is_cc: bool = False) -> SignalAnalysis:
    sample = SignalSample(
        timestamp_s=600.0,
        voltage_v=16.3,
        current_a=0.8,
        temp_c=25.0,
        is_cv=is_cv,
        is_cc=is_cc,
    )
    metrics = SignalMetrics(
        d_voltage_v_per_min=-0.01 if is_cc else 0.0,
        d_current_a_per_min=0.01 if is_cv else 0.0,
        d_temp_c_per_min=0.0,
        current_min_a=0.5 if is_cv else None,
        seconds_since_current_min=300.0 if is_cv else None,
        delta_current_from_min_a=0.3 if is_cv else None,
        reversal_threshold_a=0.15 if is_cv else None,
        current_plateau_span_a=0.02 if is_cv else None,
        current_plateau_center_a=0.5 if is_cv else None,
        reversal_confirmations=3 if is_cv else 0,
        voltage_max_v=16.35 if is_cc else None,
        seconds_since_voltage_max=300.0 if is_cc else None,
        delta_voltage_from_max_v=0.05 if is_cc else None,
        voltage_reversal_threshold_v=0.03 if is_cc else None,
        voltage_reversal_confirmations=3 if is_cc else 0,
    )
    return SignalAnalysis(sample=sample, metrics=metrics, events=frozenset(events))


class RecoveryDecisionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = RecoveryDecisionPolicy()

    def test_clean_cv_hv_reversal_finishes_stage(self):
        result = self.policy.decide(
            analysis_with(
                SignalEvent.CURRENT_REVERSAL_CONFIRMED,
                SignalEvent.END_OF_CHARGE_LIKELY,
            ),
            stage="Mix Mode",
        )
        self.assertEqual(result.decision, RecoveryDecision.FINISH_STAGE)
        self.assertIn("cv_current_reversal", result.reason)

    def test_clean_cc_voltage_reversal_finishes_stage(self):
        result = self.policy.decide(
            analysis_with(
                SignalEvent.VOLTAGE_REVERSAL_CONFIRMED,
                SignalEvent.END_OF_CHARGE_LIKELY,
                is_cv=False,
                is_cc=True,
            ),
            stage="Mix Mode",
        )
        self.assertEqual(result.decision, RecoveryDecision.FINISH_STAGE)
        self.assertIn("cc_voltage_reversal", result.reason)

    def test_thermal_acceleration_beats_end_of_charge(self):
        result = self.policy.decide(
            analysis_with(
                SignalEvent.CURRENT_REVERSAL_CONFIRMED,
                SignalEvent.END_OF_CHARGE_LIKELY,
                SignalEvent.THERMAL_ACCELERATION,
            ),
            stage="Mix Mode",
        )
        self.assertEqual(result.decision, RecoveryDecision.PAUSE_THERMAL)

    def test_cc_thermal_acceleration_is_mode_specific(self):
        result = self.policy.decide(
            analysis_with(
                SignalEvent.VOLTAGE_REVERSAL_CONFIRMED,
                SignalEvent.END_OF_CHARGE_LIKELY,
                SignalEvent.THERMAL_ACCELERATION,
                is_cv=False,
                is_cc=True,
            ),
            stage="Mix Mode",
        )
        self.assertEqual(result.decision, RecoveryDecision.PAUSE_THERMAL)
        self.assertIn("cc_voltage_fall", result.reason)

    def test_voltage_sag_beats_end_of_charge(self):
        result = self.policy.decide(
            analysis_with(
                SignalEvent.CURRENT_REVERSAL_CONFIRMED,
                SignalEvent.END_OF_CHARGE_LIKELY,
                SignalEvent.VOLTAGE_SAG_DURING_REVERSAL,
            ),
            stage="Десульфатация",
        )
        self.assertEqual(result.decision, RecoveryDecision.REST_AND_DIAGNOSE)

    def test_invalid_telemetry_fails_closed(self):
        result = self.policy.decide(
            analysis_with(SignalEvent.TELEMETRY_INVALID),
            stage="Main Charge",
        )
        self.assertEqual(result.decision, RecoveryDecision.HOLD_OUTPUT_OFF)

    def test_main_plateau_does_not_force_desulfation(self):
        result = self.policy.decide(
            analysis_with(SignalEvent.CURRENT_PLATEAU),
            stage="Main Charge",
        )
        self.assertEqual(result.decision, RecoveryDecision.CONTINUE)
        self.assertIn("not_forced_escalation", result.reason)

    def test_hv_plateau_waits_for_imin_or_reversal_in_cv(self):
        result = self.policy.decide(
            analysis_with(SignalEvent.CURRENT_PLATEAU),
            stage="conditioning",
            intent=ChargeIntent.RECOVERY,
        )
        self.assertEqual(result.decision, RecoveryDecision.CONTINUE)
        self.assertIn("observe", result.reason)


if __name__ == "__main__":
    unittest.main()
