import unittest

from recovery_shadow import ShadowRecoveryRuntime
from recovery_session import RecoveryTracePoint


class RecoveryShadowRuntimeTests(unittest.TestCase):
    def test_shadow_runtime_never_mutates_legacy_actions(self):
        runtime = ShadowRecoveryRuntime(battery_id="b1", started_at=0.0)
        actions = {"set_voltage": 16.5, "set_current": 1.0}
        original = dict(actions)
        runtime.observe(
            RecoveryTracePoint(0, "Mix Mode", 16.4, 0.5, 25.0, True, 16.5),
            legacy_actions=actions,
        )
        self.assertEqual(actions, original)

    def test_clean_reversal_flags_legacy_continue_disagreement(self):
        runtime = ShadowRecoveryRuntime(battery_id="b1", started_at=0.0)
        points = [
            RecoveryTracePoint(0, "Mix Mode", 16.40, 0.40, 25.0, True, 16.5),
            RecoveryTracePoint(120, "Mix Mode", 16.47, 0.20, 25.0, True, 16.5),
            RecoveryTracePoint(240, "Mix Mode", 16.49, 0.20, 25.0, True, 16.5),
            RecoveryTracePoint(300, "Mix Mode", 16.49, 0.27, 25.1, True, 16.5),
            RecoveryTracePoint(360, "Mix Mode", 16.49, 0.28, 25.1, True, 16.5),
            RecoveryTracePoint(420, "Mix Mode", 16.49, 0.29, 25.1, True, 16.5),
        ]
        last = None
        for point in points:
            last = runtime.observe(point, legacy_actions={})
        self.assertEqual(last.decision.decision.value, "finish_stage")
        self.assertEqual(last.disagreement, "v2_would_finish_stage")
        self.assertEqual(runtime.summary()["disagreement_counts"]["v2_would_finish_stage"], 1)

    def test_invalid_telemetry_flags_missing_output_off(self):
        runtime = ShadowRecoveryRuntime(battery_id="b1", started_at=0.0)
        record = runtime.observe(
            RecoveryTracePoint(0, "Main Charge", 0.0, 1.0, 25.0, True, 14.8),
            legacy_actions={},
        )
        self.assertEqual(record.decision.decision.value, "hold_output_off")
        self.assertEqual(record.disagreement, "v2_requires_output_off")

    def test_legacy_emergency_stop_agrees_with_v2_fail_closed(self):
        runtime = ShadowRecoveryRuntime(battery_id="b1", started_at=0.0)
        record = runtime.observe(
            RecoveryTracePoint(0, "Main Charge", 0.0, 1.0, 25.0, True, 14.8),
            legacy_actions={"emergency_stop": True},
        )
        self.assertIsNone(record.disagreement)


if __name__ == "__main__":
    unittest.main()
