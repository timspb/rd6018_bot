import unittest

from ai_engine import format_ai_snapshot
from charge_logic import ChargeController


class _FakeHass:
    pass


class AiMixPolicyTests(unittest.TestCase):
    def test_mix_snapshot_exposes_delta_as_primary_exit(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_EFB, 70)
        controller.current_stage = ChargeController.STAGE_MIX
        controller.finish_timer_start = None

        snapshot = controller.get_ai_stage_snapshot()

        self.assertIn("mix_exit_policy", snapshot)
        self.assertEqual(snapshot["mix_exit_policy"]["primary"], "delta")
        self.assertEqual(snapshot["mix_exit_policy"]["mode"], "delta_or_time_fallback")
        self.assertEqual(snapshot["mix_exit_policy"]["fallback_limit_hours"], 10)

        text = format_ai_snapshot(snapshot)
        self.assertIn("Mix exit: primary=delta", text)
        self.assertIn("normal exit is by ΔV/ΔI confirmation", text)
        self.assertIn("Finish timer active: NO", text)

    def test_mix_snapshot_reports_timer_after_delta_confirmation(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 60)
        controller.current_stage = ChargeController.STAGE_MIX
        controller.finish_timer_start = 1_000.0

        snapshot = controller.get_ai_stage_snapshot()

        self.assertTrue(snapshot["finish_timer_active"])
        self.assertEqual(snapshot["mix_exit_policy"]["mode"], "delta_confirmed_timer_running")
        self.assertEqual(snapshot["mix_exit_policy"]["primary"], "timer")

        text = format_ai_snapshot(snapshot)
        self.assertIn("Finish timer active: YES", text)


if __name__ == "__main__":
    unittest.main()
