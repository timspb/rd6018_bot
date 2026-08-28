import unittest

from pb_domain import BatteryCondition, ChargeIntent
from recovery_session import RecoverySessionTracker, RecoveryTracePoint, replay_trace
from signal_analyzer import SignalEvent


class RecoverySessionTrackerTests(unittest.TestCase):
    def test_main_and_hv_evidence_are_aggregated(self):
        tracker = RecoverySessionTracker(
            battery_id="bat-1",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.REHYDRATED,
        )

        main = [
            RecoveryTracePoint(0, "Main Charge", 13.8, 4.0, 25.0, False, 14.8, 10.0),
            RecoveryTracePoint(300, "Main Charge", 14.65, 1.0, 25.2, True, 14.8, 10.4),
            RecoveryTracePoint(600, "Main Charge", 14.78, 0.5, 25.4, True, 14.8, 10.7),
        ]
        for point in main:
            tracker.observe(point)

        self.assertAlmostEqual(tracker.evidence.main_target_v, 14.8)
        self.assertAlmostEqual(tracker.evidence.main_imin_a, 0.5)
        self.assertAlmostEqual(tracker.evidence.main_time_to_target_s, 300.0)
        self.assertAlmostEqual(tracker.evidence.main_ah_in, 0.7)

        hv_points = [
            RecoveryTracePoint(900, "Mix Mode", 16.35, 0.40, 25.5, True, 16.5),
            RecoveryTracePoint(1020, "Mix Mode", 16.45, 0.20, 25.6, True, 16.5),
            RecoveryTracePoint(1140, "Mix Mode", 16.48, 0.20, 25.7, True, 16.5),
            RecoveryTracePoint(1260, "Mix Mode", 16.49, 0.27, 25.8, True, 16.5),
            RecoveryTracePoint(1320, "Mix Mode", 16.49, 0.28, 25.8, True, 16.5),
            RecoveryTracePoint(1380, "Mix Mode", 16.49, 0.29, 25.9, True, 16.5),
        ]
        last = None
        for point in hv_points:
            last = tracker.observe(point)

        self.assertAlmostEqual(tracker.evidence.hv_target_v, 16.5)
        self.assertAlmostEqual(tracker.evidence.hv_imin_a, 0.20)
        self.assertIsNotNone(tracker.evidence.hv_time_to_target_s)
        self.assertIsNotNone(tracker.evidence.hv_reversal_delta_a)
        self.assertTrue(last.has(SignalEvent.END_OF_CHARGE_LIKELY))
        self.assertGreaterEqual(tracker.evidence.temp_max_c, 25.9)

    def test_relaxation_windows_are_recorded_once(self):
        tracker = RecoverySessionTracker(
            battery_id="bat-1",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
        )
        points = [
            RecoveryTracePoint(1000, "relax", 13.6, 0.0, 25.0),
            RecoveryTracePoint(1300, "relax", 13.2, 0.0, 24.9),
            RecoveryTracePoint(1900, "relax", 13.0, 0.0, 24.8),
            RecoveryTracePoint(4600, "relax", 12.9, 0.0, 24.7),
        ]
        for point in points:
            tracker.observe(point)

        self.assertAlmostEqual(tracker.evidence.relax_v_5m, 13.2)
        self.assertAlmostEqual(tracker.evidence.relax_v_15m, 13.0)
        self.assertAlmostEqual(tracker.evidence.relax_v_1h, 12.9)
        self.assertIsNone(tracker.evidence.relax_v_12h)

    def test_invalid_sample_does_not_poison_evidence(self):
        tracker = RecoverySessionTracker(
            battery_id="bat-1",
            started_at=0.0,
            intent=ChargeIntent.NORMAL,
        )
        analysis = tracker.observe(
            RecoveryTracePoint(0, "Main Charge", 0.0, 1.0, 25.0, True, 14.8)
        )
        self.assertTrue(analysis.has(SignalEvent.TELEMETRY_INVALID))
        self.assertIsNone(tracker.evidence.main_imin_a)
        self.assertIsNone(tracker.evidence.temp_start_c)

    def test_replay_accepts_json_shaped_mappings(self):
        evidence = replay_trace(
            [
                {
                    "timestamp_s": 0,
                    "stage": "Main Charge",
                    "voltage_v": 14.5,
                    "current_a": 1.2,
                    "temp_c": 23.0,
                    "is_cv": True,
                    "target_voltage_v": 14.8,
                    "ah": 4.0,
                },
                {
                    "timestamp_s": 300,
                    "stage": "Main Charge",
                    "voltage_v": 14.7,
                    "current_a": 0.8,
                    "temp_c": 23.2,
                    "is_cv": True,
                    "target_voltage_v": 14.8,
                    "ah": 4.2,
                },
            ],
            battery_id="bat-json",
            started_at=0,
            intent=ChargeIntent.RECOVERY,
        )
        self.assertEqual(evidence.battery_id, "bat-json")
        self.assertAlmostEqual(evidence.main_imin_a, 0.8)
        self.assertAlmostEqual(evidence.main_time_to_target_s, 300.0)

    def test_voltage_step_resets_signal_segment_without_erasing_cycle_minima(self):
        tracker = RecoverySessionTracker(
            battery_id="agm",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
        )
        tracker.observe(RecoveryTracePoint(0, "Main Charge", 14.35, 0.6, 25.0, True, 14.4))
        tracker.observe(RecoveryTracePoint(300, "Main Charge", 14.4, 0.4, 25.1, True, 14.4))
        tracker.observe(RecoveryTracePoint(600, "Main Charge", 14.55, 0.8, 25.2, True, 14.6))
        tracker.observe(RecoveryTracePoint(900, "Main Charge", 14.6, 0.5, 25.3, True, 14.6))

        # The segment-local analyzer resets at the voltage step; the aggregate
        # cycle evidence keeps the best Imin seen during Main.
        self.assertAlmostEqual(tracker.evidence.main_imin_a, 0.4)
        self.assertAlmostEqual(tracker.evidence.main_target_v, 14.6)


if __name__ == "__main__":
    unittest.main()
