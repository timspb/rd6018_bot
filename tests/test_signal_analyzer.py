import unittest

from signal_analyzer import (
    SignalAnalyzer,
    SignalAnalyzerConfig,
    SignalEvent,
    SignalSample,
)


class SignalAnalyzerTests(unittest.TestCase):
    def test_cv_imin_then_slow_current_reversal_is_eoc_evidence(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.3)

        samples = [
            SignalSample(0, 16.28, 1.00, 25.0, True),
            SignalSample(60, 16.30, 0.70, 25.0, True),
            SignalSample(120, 16.30, 0.50, 25.0, True),
            SignalSample(180, 16.30, 0.50, 25.0, True),
            SignalSample(240, 16.30, 0.66, 25.0, True),
            SignalSample(300, 16.30, 0.67, 25.0, True),
            SignalSample(360, 16.30, 0.68, 25.1, True),
        ]

        result = None
        for sample in samples:
            result = analyzer.observe(sample)

        assert result is not None
        self.assertIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, result.events)
        self.assertIn(SignalEvent.END_OF_CHARGE_LIKELY, result.events)
        self.assertNotIn(SignalEvent.THERMAL_ACCELERATION, result.events)
        self.assertAlmostEqual(result.metrics.current_min_a, 0.50)
        self.assertAlmostEqual(result.metrics.reversal_threshold_a, 0.15)

    def test_current_reversal_plus_temperature_acceleration_is_not_eoc(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.3)

        samples = [
            SignalSample(0, 16.30, 0.50, 25.0, True),
            SignalSample(60, 16.30, 0.50, 25.1, True),
            SignalSample(120, 16.30, 0.50, 25.2, True),
            SignalSample(180, 16.30, 0.66, 25.8, True),
            SignalSample(240, 16.30, 0.68, 26.5, True),
            SignalSample(300, 16.30, 0.72, 27.3, True),
        ]

        result = None
        for sample in samples:
            result = analyzer.observe(sample)

        assert result is not None
        self.assertIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, result.events)
        self.assertIn(SignalEvent.THERMAL_ACCELERATION, result.events)
        self.assertNotIn(SignalEvent.END_OF_CHARGE_LIKELY, result.events)

    def test_reversal_with_voltage_sag_is_suspicious(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.3)
        samples = [
            SignalSample(0, 16.30, 0.50, 25.0, True),
            SignalSample(60, 16.30, 0.50, 25.0, True),
            SignalSample(120, 16.30, 0.50, 25.0, True),
            SignalSample(180, 16.25, 0.66, 25.0, True),
            SignalSample(240, 16.20, 0.67, 25.0, True),
            SignalSample(300, 16.10, 0.68, 25.0, True),
        ]
        result = None
        for sample in samples:
            result = analyzer.observe(sample)
        assert result is not None
        self.assertIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, result.events)
        self.assertIn(SignalEvent.VOLTAGE_SAG_DURING_REVERSAL, result.events)
        self.assertNotIn(SignalEvent.END_OF_CHARGE_LIKELY, result.events)

    def test_missing_or_out_of_order_telemetry_is_explicitly_invalid(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("main", target_voltage_v=14.7)
        ok = analyzer.observe(SignalSample(60, 14.7, 1.0, 25.0, True))
        self.assertNotIn(SignalEvent.TELEMETRY_INVALID, ok.events)
        invalid = analyzer.observe(SignalSample(60, 14.7, 1.0, 25.0, True))
        self.assertIn(SignalEvent.TELEMETRY_INVALID, invalid.events)
        self.assertAlmostEqual(invalid.metrics.reversal_threshold_a, 0.30)

    def test_reversal_absolute_term_is_measurement_floor_for_tiny_imin(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.3)
        result = analyzer.observe(SignalSample(0, 16.3, 0.05, 25.0, True))
        # 30% of 0.05 A would be 0.015 A, below the configured observation floor.
        self.assertAlmostEqual(result.metrics.reversal_threshold_a, 0.03)

    def test_reversal_relative_term_dominates_above_measurement_floor(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.3)
        result = analyzer.observe(SignalSample(0, 16.3, 2.0, 25.0, True))
        self.assertAlmostEqual(result.metrics.reversal_threshold_a, 0.60)

    def test_current_minimum_hysteresis_is_configurable_instrument_floor(self):
        analyzer = SignalAnalyzer(
            SignalAnalyzerConfig(current_min_update_hysteresis_a=0.02)
        )
        analyzer.reset_stage("mix", target_voltage_v=16.3)
        first = analyzer.observe(SignalSample(0, 16.3, 0.50, 25.0, True))
        self.assertAlmostEqual(first.metrics.current_min_a, 0.50)

        # 0.01 A movement is below the explicitly configured sensor hysteresis.
        second = analyzer.observe(SignalSample(60, 16.3, 0.49, 25.0, True))
        self.assertAlmostEqual(second.metrics.current_min_a, 0.50)
        self.assertNotIn(SignalEvent.CURRENT_MINIMUM_UPDATED, second.events)

        third = analyzer.observe(SignalSample(120, 16.3, 0.47, 25.0, True))
        self.assertAlmostEqual(third.metrics.current_min_a, 0.47)
        self.assertIn(SignalEvent.CURRENT_MINIMUM_UPDATED, third.events)


if __name__ == "__main__":
    unittest.main()
