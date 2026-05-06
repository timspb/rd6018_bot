import unittest

from ai_engine import format_ai_snapshot
from charge_logic import ChargeController


class _FakeHass:
    pass


class StagePathTests(unittest.TestCase):
    def test_ai_snapshot_exposes_previous_stage_and_path(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 70)
        controller.current_stage = ChargeController.STAGE_MAIN
        controller.current_stage = ChargeController.STAGE_MIX

        snapshot = controller.get_ai_stage_snapshot(25.0)
        text = format_ai_snapshot(snapshot)

        self.assertEqual(snapshot["previous_stage"], ChargeController.STAGE_MAIN)
        self.assertIn(ChargeController.STAGE_PREP, snapshot["stage_path"])
        self.assertEqual(snapshot["stage_path"][-2:], [ChargeController.STAGE_MAIN, ChargeController.STAGE_MIX])
        self.assertIn("Previous stage:", text)
        self.assertIn("Stage path:", text)


if __name__ == "__main__":
    unittest.main()
