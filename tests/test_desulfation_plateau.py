import asyncio
import unittest

from charge_logic import ChargeController


class _FakeHass:
    pass


class DesulfationPlateauTests(unittest.TestCase):
    def setUp(self):
        self.controller = ChargeController(_FakeHass())
        self.controller.start(ChargeController.PROFILE_EFB, 60)
        self.controller.current_stage = ChargeController.STAGE_MAIN
        self.controller.stage_start_time = 0.0
        self.controller.total_start_time = 0.0

    def _tick(self, *, now: float, current: float):
        original_time = __import__("time").time
        __import__("time").time = lambda: now
        try:
            return asyncio.run(
                self.controller.tick(
                    voltage=14.8,
                    current=current,
                    temp_ext=23.0,
                    is_cv=True,
                    ah=0.5,
                    output_is_on=True,
                    manual_off_active=False,
                )
            )
        finally:
            __import__("time").time = original_time

    def test_gradual_current_drop_does_not_start_desulfation(self):
        points = [
            (301.0, 0.60),
            (901.0, 0.55),
            (1501.0, 0.50),
            (2101.0, 0.45),
            (2701.0, 0.40),
            (3301.0, 0.35),
        ]

        for now, current in points:
            actions = self._tick(now=now, current=current)

        self.assertEqual(self.controller.current_stage, ChargeController.STAGE_MAIN)
        self.assertNotIn("notify", actions)
        self.assertAlmostEqual(self.controller._stuck_current_value, 0.35)
        self.assertAlmostEqual(self.controller._stuck_current_since, 3301.0)

    def test_flat_current_above_threshold_starts_desulfation(self):
        self._tick(now=301.0, current=0.60)
        actions = self._tick(now=2701.0, current=0.60)

        self.assertEqual(self.controller.current_stage, ChargeController.STAGE_DESULFATION)
        self.assertIn("десульфатация", actions.get("notify", "").lower())
        self.assertEqual(self.controller.antisulfate_count, 1)


if __name__ == "__main__":
    unittest.main()
