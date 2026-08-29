import unittest

from battery_diagnostics import SpecificGravityMeasurement, assess_specific_gravity
from battery_fault_engine import (
    BatteryFaultContext,
    DiagnosticAuthority,
    assess_battery_fault,
)
from battery_diagnostics import DiagnosticHypothesis, DiagnosticLevel


class BatteryFaultEngineTests(unittest.TestCase):
    def test_first_sg_imbalance_requests_verification_not_hv_block(self):
        sg = assess_specific_gravity(
            SpecificGravityMeasurement.from_iterable(
                battery_id="flooded",
                measured_at=100.0,
                cells=(1.275, 1.272, 1.270, 1.220, 1.274, 1.271),
            )
        )
        result = assess_battery_fault(BatteryFaultContext(specific_gravity=sg))
        self.assertEqual(result.authority, DiagnosticAuthority.VERIFY_BEFORE_HV)
        self.assertEqual(
            result.evidence(DiagnosticHypothesis.STRATIFICATION).level,
            DiagnosticLevel.VERIFY,
        )
        self.assertLess(result.evidence(DiagnosticHypothesis.CELL_FAULT).score, 80)

    def test_persistent_sg_plus_five_cell_rest_pattern_blocks_automatic_hv(self):
        sg = assess_specific_gravity(
            SpecificGravityMeasurement.from_iterable(
                battery_id="flooded",
                measured_at=100.0,
                cells=(1.275, 1.272, 1.270, 1.205, 1.274, 1.271),
            )
        )
        result = assess_battery_fault(
            BatteryFaultContext(
                rested_ocv_v=10.55,
                fully_charged_before_rest=True,
                battery_isolated_during_rest=True,
                specific_gravity=sg,
                sg_persisted_after_corrective_equalization=True,
            )
        )
        self.assertEqual(result.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)
        self.assertIn("rested_ocv", result.independent_cell_fault_classes)
        self.assertIn("persistent_sg", result.independent_cell_fault_classes)

    def test_low_voltage_without_known_full_charge_and_isolation_is_not_cell_proof(self):
        result = assess_battery_fault(
            BatteryFaultContext(
                rested_ocv_v=10.55,
                fully_charged_before_rest=False,
                battery_isolated_during_rest=False,
            )
        )
        self.assertEqual(result.authority, DiagnosticAuthority.ALLOW)
        self.assertEqual(result.evidence(DiagnosticHypothesis.CELL_FAULT).score, 0)

    def test_recovery_improvement_is_counterevidence_for_structural_fault(self):
        result = assess_battery_fault(
            BatteryFaultContext(
                legacy_risk_score=80,
                recovery_attempts=3,
                recovery_response_improved=True,
            )
        )
        self.assertEqual(result.authority, DiagnosticAuthority.ALLOW)
        self.assertIn(
            "counterevidence_recovery_improved",
            result.evidence(DiagnosticHypothesis.CELL_FAULT).reasons,
        )
        self.assertGreater(
            result.evidence(DiagnosticHypothesis.SULFATION).score,
            result.evidence(DiagnosticHypothesis.CELL_FAULT).score,
        )

    def test_external_failed_cell_confirmation_blocks_hv_but_does_not_claim_hard_stop(self):
        result = assess_battery_fault(
            BatteryFaultContext(external_failed_cell_confirmed=True)
        )
        self.assertEqual(result.authority, DiagnosticAuthority.BLOCK_AUTOMATIC_HV)
        self.assertNotEqual(result.authority, DiagnosticAuthority.HARD_STOP)
        self.assertEqual(result.evidence(DiagnosticHypothesis.CELL_FAULT).score, 100)

    def test_two_wire_dynamic_loop_worsening_also_raises_path_hypothesis(self):
        result = assess_battery_fault(
            BatteryFaultContext(dynamic_loop_worsened=True)
        )
        self.assertGreater(
            result.evidence(DiagnosticHypothesis.CHARGER_PATH).score,
            0,
        )
        self.assertGreater(
            result.evidence(DiagnosticHypothesis.CAPACITY_LOSS).score,
            0,
        )
        self.assertEqual(result.authority, DiagnosticAuthority.ALLOW)


if __name__ == "__main__":
    unittest.main()
