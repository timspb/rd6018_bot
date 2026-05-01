import time
import unittest

from ai_engine import format_ai_snapshot
from charge_logic import ChargeController


class _FakeHass:
    pass


class PostChargeRelaxationTests(unittest.TestCase):
    def test_safe_wait_snapshot_reports_relaxation_signal(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_EFB, 70)

        now = time.time()
        controller.current_stage = ChargeController.STAGE_SAFE_WAIT
        controller.stage_start_time = now - 1800
        controller._safe_wait_start = now - 1800
        controller._safe_wait_target_v = 13.6
        controller._safe_wait_target_i = 0.0
        controller._safe_wait_v_samples.clear()
        controller._safe_wait_v_samples.extend(
            [
                (now - 1800, 14.46, 0.02, 24.8),
                (now - 1200, 14.38, 0.02, 24.9),
                (now - 600, 14.31, 0.01, 25.0),
                (now, 14.23, 0.01, 25.0),
            ]
        )

        snapshot = controller.get_ai_stage_snapshot()
        relaxation = snapshot["post_charge_relaxation"]

        self.assertIsNotNone(relaxation)
        self.assertEqual(relaxation["status"], "watch")
        self.assertEqual(relaxation["stratification_risk"], "medium")
        self.assertGreater(relaxation["decay_mv_min"], 4.0)
        self.assertLessEqual(relaxation["temp_span_c"], 0.6)

        text = format_ai_snapshot(snapshot)
        self.assertIn("Post-charge: status=watch", text)
        self.assertIn("risk=medium", text)

    def test_agm_profile_is_stricter_on_relaxation(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_AGM, 70)

        now = time.time()
        controller.current_stage = ChargeController.STAGE_SAFE_WAIT
        controller.stage_start_time = now - 2400
        controller._safe_wait_start = now - 2400
        controller._safe_wait_target_v = 13.6
        controller._safe_wait_target_i = 0.0
        controller._safe_wait_v_samples.clear()
        controller._safe_wait_v_samples.extend(
            [
                (now - 2400, 14.40, 0.02, 24.8),
                (now - 1800, 14.37, 0.02, 24.9),
                (now - 1200, 14.35, 0.01, 25.0),
                (now - 600, 14.33, 0.01, 25.1),
                (now, 14.31, 0.01, 25.1),
            ]
        )

        snapshot = controller.get_ai_stage_snapshot()
        relaxation = snapshot["post_charge_relaxation"]

        self.assertIsNotNone(relaxation)
        self.assertEqual(relaxation["profile"], ChargeController.PROFILE_AGM)
        self.assertEqual(relaxation["status"], "stable")
        self.assertEqual(relaxation["stratification_risk"], "very_low")
        self.assertLess(relaxation["decay_mv_min"], 5.5)

    def test_cac_profile_flags_moderate_decay_quickly(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 70)

        now = time.time()
        controller.current_stage = ChargeController.STAGE_SAFE_WAIT
        controller.stage_start_time = now - 1800
        controller._safe_wait_start = now - 1800
        controller._safe_wait_target_v = 13.6
        controller._safe_wait_target_i = 0.0
        controller._safe_wait_v_samples.clear()
        controller._safe_wait_v_samples.extend(
            [
                (now - 1800, 14.50, 0.02, 24.8),
                (now - 1200, 14.43, 0.02, 24.9),
                (now - 600, 14.36, 0.01, 24.9),
                (now, 14.28, 0.01, 25.0),
            ]
        )

        snapshot = controller.get_ai_stage_snapshot()
        relaxation = snapshot["post_charge_relaxation"]

        self.assertIsNotNone(relaxation)
        self.assertEqual(relaxation["profile"], ChargeController.PROFILE_CA)
        self.assertEqual(relaxation["status"], "watch")
        self.assertEqual(relaxation["stratification_risk"], "medium")
        self.assertGreaterEqual(relaxation["decay_mv_min"], 3.5)


if __name__ == "__main__":
    unittest.main()
