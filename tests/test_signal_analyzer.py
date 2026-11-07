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
        self.assertIsNone(result.metrics.voltage_max_v)

    def test_cc_vmax_then_voltage_fall_is_eoc_evidence(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.5)

        samples = [
            SignalSample(0, 15.90, 1.50, 25.0, is_cc=True),
            SignalSample(60, 16.10, 1.50, 25.0, is_cc=True),
            SignalSample(120, 16.30, 1.50, 25.0, is_cc=True),
            SignalSample(180, 16.29, 1.50, 25.0, is_cc=True),
            SignalSample(240, 16.26, 1.50, 25.0, is_cc=True),
            SignalSample(300, 16.25, 1.50, 25.0, is_cc=True),
            SignalSample(360, 16.24, 1.50, 25.1, is_cc=True),
        ]

        result = None
        for sample in samples:
            result = analyzer.observe(sample)

        assert result is not None
        self.assertIn(SignalEvent.VOLTAGE_REVERSAL_CONFIRMED, result.events)
        self.assertIn(SignalEvent.END_OF_CHARGE_LIKELY, result.events)
        self.assertNotIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, result.events)
        self.assertIsNone(result.metrics.current_min_a)
        self.assertAlmostEqual(result.metrics.voltage_max_v, 16.30)
        self.assertAlmostEqual(result.metrics.delta_voltage_from_max_v, 0.06)
        self.assertAlmostEqual(result.metrics.voltage_reversal_threshold_v, 0.03)

    def test_current_reversal_plus_temperature_acceleration_is_not_eoc(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.3)

        samples = [
            SignalSample(0, 16.30, 0.50, 30.0, True),
            SignalSample(60, 16.30, 0.50, 30.1, True),
            SignalSample(120, 16.30, 0.50, 30.2, True),
            SignalSample(180, 16.30, 0.66, 30.8, True),
            SignalSample(240, 16.30, 0.68, 31.5, True),
            SignalSample(300, 16.30, 0.72, 32.3, True),
        ]

        result = None
        for sample in samples:
            result = analyzer.observe(sample)

        assert result is not None
        self.assertIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, result.events)
        self.assertIn(SignalEvent.THERMAL_ACCELERATION, result.events)
        self.assertNotIn(SignalEvent.END_OF_CHARGE_LIKELY, result.events)

    def test_cc_voltage_fall_plus_temperature_acceleration_is_not_eoc(self):
        analyzer = SignalAnalyzer()
        analyzer.reset_stage("mix", target_voltage_v=16.5)
        samples = [
            SignalSample(0, 16.30, 1.50, 30.0, is_cc=True),
            SignalSample(60, 16.29, 1.50, 30.2, is_cc=True),
            SignalSample(120, 16.26, 1.50, 30.6, is_cc=True),
            SignalSample(180, 16.25, 1.50, 31.1, is_cc=True),
            SignalSample(240, 16.24, 1.50, 31.7, is_cc=True),
        ]
        result = None
        for sample in samples:
            result = analyzer.observe(sample)
        assert result is not None
        self.assertIn(SignalEvent.VOLTAGE_REVERSAL_CONFIRMED, result.events)
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

    def test_mix_cv_reversal_is_bounded_by_stage_current_setpoint(self):
        analyzer = SignalAnalyzer()
        analyzer.current_limit_a = 2.40
        analyzer.reset_stage("mix mode", target_voltage_v=16.5)
        readings = [
            (0, 2.18), (60, 2.18), (120, 2.18), (180, 2.39),
            (240, 2.40), (300, 2.40), (360, 2.40),
        ]
        results = [
            analyzer.observe(SignalSample(t, 16.5, i, 25.0, is_cv=True))
            for t, i in readings
        ]
        self.assertAlmostEqual(results[0].metrics.reversal_threshold_a, 0.22)
        self.assertNotIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, results[3].events)
        self.assertIn(SignalEvent.CURRENT_REVERSAL_CONFIRMED, results[-1].events)
        self.assertIn(SignalEvent.END_OF_CHARGE_LIKELY, results[-1].events)

    def test_mix_cv_near_limit_below_noise_floor_cannot_confirm_reversal(self):
        analyzer = SignalAnalyzer()
        analyzer.current_limit_a = 2.40
        analyzer.reset_stage("mix", target_voltage_v=16.5)
        samples = [(0, 2.39), (60, 2.39), (180, 2.40),
                   (240, 2.40), (300, 2.40), (360, 2.40)]
        results = [
            analyzer.observe(SignalSample(t, 16.5, i, 25.0, is_cv=True))
            for t, i in samples
        ]
        self.assertIsNone(results[-1].metrics.reversal_threshold_a)
        self.assertFalse(any(
            SignalEvent.CURRENT_REVERSAL_CONFIRMED in result.events
            for result in results
        ))

    def test_main_stage_does_not_cap_current_reversal_threshold(self):
        analyzer = SignalAnalyzer()
        analyzer.current_limit_a = 2.40
        analyzer.reset_stage("main", target_voltage_v=14.8)
        result = analyzer.observe(SignalSample(0, 14.8, 2.18, 25.0, is_cv=True))
        self.assertAlmostEqual(result.metrics.reversal_threshold_a, 0.654)

    def test_mix_cc_current_limit_does_not_create_cv_delta(self):
        analyzer = SignalAnalyzer()
        analyzer.current_limit_a = 2.40
        analyzer.reset_stage("mix", target_voltage_v=16.5)
        results = [
            analyzer.observe(SignalSample(t, v, 2.40, 25.0, is_cc=True))
            for t, v in [(0, 16.4), (60, 16.5), (180, 16.5), (240, 16.5)]
        ]
        self.assertFalse(any(
            SignalEvent.CURRENT_REVERSAL_CONFIRMED in result.events
            for result in results
        ))
        self.assertIsNone(results[-1].metrics.current_min_a)

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

    def test_cc_voltage_maximum_hysteresis_is_configurable_instrument_floor(self):
        analyzer = SignalAnalyzer(
            SignalAnalyzerConfig(voltage_max_update_hysteresis_v=0.02)
        )
        analyzer.reset_stage("mix", target_voltage_v=16.5)
        first = analyzer.observe(SignalSample(0, 16.30, 1.0, 25.0, is_cc=True))
        self.assertAlmostEqual(first.metrics.voltage_max_v, 16.30)

        second = analyzer.observe(SignalSample(60, 16.31, 1.0, 25.0, is_cc=True))
        self.assertAlmostEqual(second.metrics.voltage_max_v, 16.30)
        self.assertNotIn(SignalEvent.VOLTAGE_MAXIMUM_UPDATED, second.events)

        third = analyzer.observe(SignalSample(120, 16.33, 1.0, 25.0, is_cc=True))
        self.assertAlmostEqual(third.metrics.voltage_max_v, 16.33)
        self.assertIn(SignalEvent.VOLTAGE_MAXIMUM_UPDATED, third.events)


if __name__ == "__main__":
    unittest.main()
