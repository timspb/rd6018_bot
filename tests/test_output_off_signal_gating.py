import unittest

from pb_domain import BatteryCondition, ChargeIntent
from recovery_shadow import ShadowRecoveryRuntime
from recovery_session import RecoveryTracePoint


class OutputOffSignalGatingTests(unittest.TestCase):
    def _runtime(self):
        return ShadowRecoveryRuntime(
            battery_id="live-battery",
            started_at=1000.0,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.UNKNOWN,
        )

    def test_output_off_main_sample_does_not_seed_zero_imin(self):
        runtime = self._runtime()

        off = runtime.observe(
            RecoveryTracePoint(
                timestamp_s=1000.0,
                stage="Main Charge",
                voltage_v=13.7,
                current_a=0.0,
                temp_c=26.0,
                is_cv=True,
                is_cc=False,
                target_voltage_v=14.7,
                ah=16.4,
            ),
            output_is_on=False,
        )
        self.assertIsNone(off.analysis.metrics.current_min_a)
        self.assertEqual(off.decision.decision.value, "continue")
        self.assertEqual(off.decision.reason, "output_already_off")

        on = runtime.observe(
            RecoveryTracePoint(
                timestamp_s=1060.0,
                stage="Main Charge",
                voltage_v=14.67,
                current_a=0.80,
                temp_c=26.0,
                is_cv=True,
                is_cc=False,
                target_voltage_v=14.7,
                ah=16.4,
            ),
            output_is_on=True,
        )
        self.assertAlmostEqual(on.analysis.metrics.current_min_a, 0.80)
        self.assertAlmostEqual(on.analysis.metrics.seconds_since_current_min, 0.0)
        self.assertAlmostEqual(runtime.tracker.evidence.main_imin_a, 0.80)

    def test_output_off_hv_sample_does_not_seed_cc_vmax(self):
        runtime = self._runtime()
        off = runtime.observe(
            RecoveryTracePoint(
                timestamp_s=1000.0,
                stage="Mix Mode",
                voltage_v=16.4,
                current_a=0.0,
                temp_c=26.0,
                is_cv=False,
                is_cc=True,
                target_voltage_v=16.5,
                ah=18.0,
            ),
            output_is_on=False,
        )
        self.assertIsNone(off.analysis.metrics.voltage_max_v)

        on = runtime.observe(
            RecoveryTracePoint(
                timestamp_s=1060.0,
                stage="Mix Mode",
                voltage_v=16.45,
                current_a=2.1,
                temp_c=26.0,
                is_cv=False,
                is_cc=True,
                target_voltage_v=16.5,
                ah=18.0,
            ),
            output_is_on=True,
        )
        self.assertAlmostEqual(on.analysis.metrics.voltage_max_v, 16.45)
        self.assertAlmostEqual(on.analysis.metrics.seconds_since_voltage_max, 0.0)

    def test_safe_wait_relaxation_still_observes_output_off(self):
        runtime = self._runtime()
        runtime.observe(
            RecoveryTracePoint(
                timestamp_s=1000.0,
                stage="Безопасное ожидание",
                voltage_v=13.0,
                current_a=0.0,
                temp_c=26.0,
                is_cv=False,
                is_cc=False,
                ah=20.0,
            ),
            output_is_on=False,
        )
        runtime.observe(
            RecoveryTracePoint(
                timestamp_s=1300.0,
                stage="Безопасное ожидание",
                voltage_v=12.8,
                current_a=0.0,
                temp_c=25.9,
                is_cv=False,
                is_cc=False,
                ah=20.0,
            ),
            output_is_on=False,
        )
        self.assertAlmostEqual(runtime.tracker.evidence.relax_v_5m, 12.8)


if __name__ == "__main__":
    unittest.main()
