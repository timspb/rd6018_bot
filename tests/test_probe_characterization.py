import unittest

from probe_characterization import (
    CharacterizationSample,
    characterization_to_mapping,
    characterize_probe_samples,
    load_characterization_jsonl,
)


class ProbeCharacterizationTests(unittest.TestCase):
    def _samples(self):
        return [
            CharacterizationSample(0.0, "baseline", 14.100, 6.00, 6.0, 14.120, 25.0, "cc"),
            CharacterizationSample(5.0, "baseline", 14.101, 6.02, 6.0, 14.121, 25.0, "cc"),
            CharacterizationSample(10.0, "baseline", 14.100, 6.01, 6.0, 14.120, 25.0, "cc"),
            CharacterizationSample(15.0, "stepped", 14.070, 3.30, 3.0, 14.090, 25.0, "cc"),
            CharacterizationSample(20.0, "stepped", 14.060, 3.05, 3.0, 14.080, 25.0, "cc"),
            CharacterizationSample(25.0, "stepped", 14.055, 3.01, 3.0, 14.075, 25.0, "cc"),
            CharacterizationSample(30.0, "stepped", 14.054, 3.00, 3.0, 14.074, 25.0, "cc"),
        ]

    def test_phase_stats_use_actual_timestamps_and_observed_steps(self) -> None:
        report = characterize_probe_samples(self._samples(), tail_count=2)
        baseline = next(phase for phase in report.phases if phase.phase == "baseline")
        self.assertAlmostEqual(baseline.cadence_median_s or 0.0, 5.0)
        self.assertAlmostEqual(baseline.battery_voltage.median, 14.100)
        self.assertAlmostEqual(baseline.battery_voltage.observed_min_step or 0.0, 0.001)

    def test_step_is_current_reduction_and_dynamic_loop_is_descriptive(self) -> None:
        report = characterize_probe_samples(self._samples(), tail_count=2)
        self.assertIsNotNone(report.step)
        step = report.step
        assert step is not None
        self.assertLess(step.delta_current_a, 0.0)
        self.assertLess(step.delta_voltage_v, 0.0)
        self.assertIsNotNone(step.dynamic_loop_mohm)
        self.assertIn("output_minus_battery_voltage_is_descriptive_not_resistance", report.warnings)
        self.assertEqual(len(step.stepped_voltage_deviation_from_tail), 4)

    def test_non_reducing_measured_step_is_flagged_not_silently_accepted(self) -> None:
        samples = [
            CharacterizationSample(0, "baseline", 14.0, 2.0),
            CharacterizationSample(5, "baseline", 14.0, 2.0),
            CharacterizationSample(10, "stepped", 14.0, 2.1),
            CharacterizationSample(15, "stepped", 14.0, 2.1),
        ]
        report = characterize_probe_samples(samples)
        self.assertIn("step_did_not_reduce_measured_current", report.warnings)

    def test_jsonl_loader_and_mapping(self) -> None:
        samples = load_characterization_jsonl(
            '{"timestamp_s":0,"phase":"baseline","battery_voltage_v":14.1,"current_a":6}\n'
            '{"timestamp_s":5,"phase":"baseline","battery_voltage_v":14.1,"current_a":6}\n'
            '{"timestamp_s":10,"phase":"stepped","battery_voltage_v":14.05,"current_a":3}\n'
            '{"timestamp_s":15,"phase":"stepped","battery_voltage_v":14.04,"current_a":3}\n'
        )
        mapped = characterization_to_mapping(characterize_probe_samples(samples))
        self.assertEqual(len(mapped["phases"]), 2)
        self.assertAlmostEqual(mapped["step"]["delta_current_a"], -3.0)

    def test_output_minus_battery_voltage_is_never_named_resistance(self) -> None:
        mapped = characterization_to_mapping(characterize_probe_samples(self._samples()))
        phase = mapped["phases"][0]
        self.assertIn("output_minus_battery_voltage", phase)
        self.assertNotIn("path_resistance", phase)
        self.assertNotIn("internal_resistance", phase)


if __name__ == "__main__":
    unittest.main()
