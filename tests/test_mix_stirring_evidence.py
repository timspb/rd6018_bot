"""Negative and positive *offline* evidence checks; no charging hardware."""
import unittest
from dataclasses import replace

from runtime.charge.observability.mix_stirring_evidence import (
    DIAGNOSTIC_CODE,
    MixEvidencePoint,
    StirringCandidateConfig,
    assess_mix_stirring,
)


def points():
    return [
        MixEvidencePoint(
            timestamp_s=float(t),
            battery_voltage_v=16.49,
            battery_current_a=0.9,  # 0.015C at 60 Ah; candidate only.
            voltage_setpoint_readback_v=16.5,
            current_setpoint_readback_a=1.8,  # 0.03C.
            battery_temperature_c=26.0 + t / 10000,
            output_on=True, is_cv=True, sources_fresh=True,
            thermal_acceleration=False, safety_clear=True,
        )
        for t in range(0, 241, 30)
    ]


def evaluate(data=None, **overrides):
    kwargs = dict(
        profile="EFB", capacity_ah=60.0, mix_started_at_s=0.0,
        configured_ceiling_v=16.5, delta_confirmed=False,
    )
    kwargs.update(overrides)
    return assess_mix_stirring(points() if data is None else data, **kwargs)


class PassiveStirringEvidenceTests(unittest.TestCase):
    def test_efb_early_low_current_is_observational_candidate(self):
        result = evaluate()
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.diagnostic_code, DIAGNOSTIC_CODE)
        self.assertAlmostEqual(result.confirmed_low_current_c, 0.015)
        self.assertFalse(result.actuator_authority)
        self.assertIsNotNone(result.temperature_rate_c_per_min)

    def test_agm_excluded_and_ca_ca_not_escalation_candidate(self):
        self.assertEqual(evaluate(profile="AGM").status, "excluded")
        self.assertEqual(evaluate(profile="Ca/Ca").status, "observational_only")
        self.assertIsNone(evaluate(profile="Ca/Ca").diagnostic_code)

    def test_after_delta_or_unknown_delta_never_candidate(self):
        for value in (True, None):
            with self.subTest(delta=value):
                a = evaluate(delta_confirmed=value)
                self.assertEqual(a.status, "insufficient_evidence")
                self.assertFalse(a.actuator_authority)

    def test_early_ceiling_must_be_physical_cv_with_verified_setpoint(self):
        cases = [
            {"battery_voltage_v": 16.35},
            {"voltage_setpoint_readback_v": 16.3},
            {"is_cv": False},
        ]
        for patch in cases:
            with self.subTest(patch=patch):
                a = evaluate([replace(p, **patch) for p in points()])
                self.assertEqual(a.reason, "ceiling_not_physically_observed")

    def test_late_ceiling_does_not_prove_fast_reach(self):
        delayed = [replace(p, timestamp_s=p.timestamp_s + 1800) for p in points()]
        self.assertEqual(evaluate(delayed).reason, "ceiling_reached_too_late")

    def test_measured_current_must_remain_below_two_percent_c(self):
        xs = points()
        xs[-1] = replace(xs[-1], battery_current_a=1.2)
        a = evaluate(xs)
        self.assertEqual(a.status, "not_candidate")
        self.assertIsNone(a.diagnostic_code)

    def test_readback_program_must_be_near_003c(self):
        xs = points()
        xs[-1] = replace(xs[-1], current_setpoint_readback_a=0.3)
        self.assertEqual(evaluate(xs).reason, "current_program_not_nominal_mix")

    def test_missing_confirmation_window_and_gap_cannot_pass(self):
        xs = [p for p in points() if p.timestamp_s not in (120, 150)]
        self.assertNotEqual(evaluate(xs).status, "candidate")
        xs = [p for p in points() if p.timestamp_s not in (120, 150, 180)]
        self.assertEqual(evaluate(xs).reason, "confirmation_gap")

    def test_unknown_or_faulted_safety_is_not_no_thermal_risk(self):
        for patch, reason in [
            ({"thermal_acceleration": True}, "thermal_acceleration_or_unassessed"),
            ({"thermal_acceleration": None}, "thermal_acceleration_or_unassessed"),
            ({"safety_clear": None}, "safety_evidence_unknown_or_fault"),
            ({"safety_clear": False}, "safety_evidence_unknown_or_fault"),
            ({"output_on": None}, "unverified_active_output_or_stale_evidence"),
            ({"sources_fresh": False}, "unverified_active_output_or_stale_evidence"),
        ]:
            with self.subTest(patch=patch):
                xs = points()
                xs[-1] = replace(xs[-1], **patch)
                self.assertEqual(evaluate(xs).reason, reason)

    def test_out_of_order_and_epoch_replay_rejected(self):
        self.assertEqual(evaluate(list(reversed(points()))).reason,
                         "out_of_order_or_wrong_epoch")
        self.assertEqual(evaluate(mix_started_at_s=45).reason,
                         "out_of_order_or_wrong_epoch")

    def test_no_samples_or_nan_fail_closed(self):
        self.assertEqual(evaluate([]).reason, "no_samples")
        xs = points()
        xs[-1] = replace(xs[-1], battery_current_a=float("nan"))
        self.assertEqual(evaluate(xs).reason, "invalid_sample")

    def test_config_is_tunable_without_any_voltage_authority(self):
        strict = StirringCandidateConfig(low_current_c=0.01)
        self.assertEqual(evaluate(config=strict).status, "not_candidate")
        self.assertFalse(evaluate(config=strict).actuator_authority)
        with self.assertRaises(ValueError):
            StirringCandidateConfig(confirmation_windows=1)


if __name__ == "__main__":
    unittest.main()
