import unittest

from first_stage_evidence import (
    FirstStageState,
    assess_first_stage,
    tail_current_threshold_a,
)
from pb_domain import BatteryChemistry


class FirstStageEvidenceTests(unittest.TestCase):
    def test_threshold_scales_with_capacity(self):
        small = tail_current_threshold_a(BatteryChemistry.EFB, 45)
        large = tail_current_threshold_a(BatteryChemistry.EFB, 200)
        self.assertAlmostEqual(small, 0.18)
        self.assertAlmostEqual(large, 0.80)
        self.assertGreater(large, small)

    def test_agm_70ah_preserves_rough_legacy_boundary(self):
        threshold = tail_current_threshold_a(BatteryChemistry.AGM, 70)
        self.assertAlmostEqual(threshold, 0.21)

    def test_low_current_is_not_tail_ready_before_cv_target(self):
        result = assess_first_stage(
            chemistry=BatteryChemistry.EFB,
            capacity_ah=70,
            voltage_v=13.9,
            current_a=0.20,
            target_voltage_v=14.8,
            is_cv=False,
        )
        self.assertEqual(result.state, FirstStageState.BULK_OR_TAPER)

    def test_cv_tail_is_ready_when_near_target(self):
        result = assess_first_stage(
            chemistry=BatteryChemistry.EFB,
            capacity_ah=70,
            voltage_v=14.72,
            current_a=0.25,
            target_voltage_v=14.8,
            is_cv=True,
        )
        self.assertEqual(result.state, FirstStageState.TAIL_READY)
        self.assertAlmostEqual(result.tail_threshold_a, 0.28)

    def test_plateau_above_tail_is_evidence_not_automatic_hv_command(self):
        result = assess_first_stage(
            chemistry=BatteryChemistry.EFB,
            capacity_ah=70,
            voltage_v=14.78,
            current_a=0.60,
            target_voltage_v=14.8,
            is_cv=True,
            plateau_minutes=45,
            required_plateau_minutes=40,
        )
        self.assertEqual(result.state, FirstStageState.STUCK_PLATEAU)
        self.assertNotIn("desulf", result.reason.lower())
        self.assertNotIn("mix", result.reason.lower())

    def test_thermal_acceleration_overrides_apparent_tail(self):
        result = assess_first_stage(
            chemistry=BatteryChemistry.AGM,
            capacity_ah=70,
            voltage_v=14.75,
            current_a=0.18,
            target_voltage_v=14.8,
            is_cv=True,
            dtemp_c_per_min=0.15,
        )
        self.assertEqual(result.state, FirstStageState.THERMALLY_UNSTABLE)

    def test_voltage_sag_overrides_stuck_plateau(self):
        result = assess_first_stage(
            chemistry=BatteryChemistry.CA_CA,
            capacity_ah=100,
            voltage_v=14.75,
            current_a=0.8,
            target_voltage_v=14.8,
            is_cv=True,
            plateau_minutes=60,
            dvoltage_v_per_min=-0.02,
        )
        self.assertEqual(result.state, FirstStageState.VOLTAGE_UNSTABLE)

    def test_small_battery_threshold_has_measurement_floor(self):
        threshold = tail_current_threshold_a(BatteryChemistry.AGM, 5)
        self.assertAlmostEqual(threshold, 0.05)


if __name__ == "__main__":
    unittest.main()
