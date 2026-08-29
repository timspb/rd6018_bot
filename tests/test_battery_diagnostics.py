import unittest

from battery_diagnostics import (
    DiagnosticLevel,
    DynamicLoopProbe,
    SpecificGravityMeasurement,
    assess_specific_gravity,
)


class BatteryDiagnosticsTests(unittest.TestCase):
    def test_balanced_sg_is_normal(self):
        measurement = SpecificGravityMeasurement.from_iterable(
            battery_id="flooded-1",
            measured_at=100.0,
            temperature_c=25.0,
            context="post_charge_rest",
            cells=(1.270, 1.272, 1.269, 1.271, 1.270, 1.268),
        )
        assessment = assess_specific_gravity(measurement)
        self.assertEqual(assessment.level, DiagnosticLevel.NORMAL)
        self.assertEqual(assessment.valid_cell_count, 6)
        self.assertLess(assessment.spread or 1.0, 0.030)

    def test_one_low_cell_escalates_to_verify_but_not_confirmed_fault(self):
        measurement = SpecificGravityMeasurement.from_iterable(
            battery_id="flooded-1",
            measured_at=100.0,
            cells=(1.275, 1.272, 1.270, 1.180, 1.274, 1.271),
        )
        assessment = assess_specific_gravity(measurement)
        self.assertEqual(assessment.level, DiagnosticLevel.VERIFY)
        self.assertEqual(assessment.low_outlier_cells, (4,))
        self.assertGreaterEqual(assessment.spread or 0.0, 0.030)

    def test_partial_sg_keeps_cell_positions_and_is_watch(self):
        measurement = SpecificGravityMeasurement.from_iterable(
            battery_id="flooded-1",
            measured_at=100.0,
            cells=(1.270, None, 1.268, None, 1.271, 1.269),
        )
        assessment = assess_specific_gravity(measurement)
        self.assertEqual(assessment.level, DiagnosticLevel.WATCH)
        self.assertEqual(assessment.valid_cell_count, 4)

    def test_sg_rejects_implausible_value(self):
        with self.assertRaises(ValueError):
            SpecificGravityMeasurement.from_iterable(
                battery_id="flooded-1",
                measured_at=100.0,
                cells=(1.27, 1.27, 1.27, 0.8, 1.27, 1.27),
            )

    def test_dynamic_probe_is_two_wire_loop_response_not_named_battery_ri(self):
        probe = DynamicLoopProbe(
            battery_id="efb-1",
            measured_at=200.0,
            stage="Main Charge",
            baseline_voltage_v=14.10,
            baseline_current_a=7.0,
            stepped_voltage_v=14.04,
            stepped_current_a=3.0,
            connection_id="session-42",
        )
        self.assertAlmostEqual(probe.delta_voltage_v, -0.06)
        self.assertAlmostEqual(probe.delta_current_a, -4.0)
        self.assertAlmostEqual(probe.dynamic_loop_mohm or 0.0, 15.0)
        self.assertEqual(probe.comparable_key, "efb-1:session-42")

    def test_probe_without_connection_id_is_not_declared_directly_comparable(self):
        probe = DynamicLoopProbe(
            battery_id="efb-1",
            measured_at=200.0,
            stage="Main Charge",
            baseline_voltage_v=14.10,
            baseline_current_a=7.0,
            stepped_voltage_v=14.04,
            stepped_current_a=3.0,
        )
        self.assertIsNone(probe.comparable_key)


if __name__ == "__main__":
    unittest.main()
