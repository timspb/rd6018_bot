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

    def _tick(self, *, now: float, current: float, is_cv: bool = True, controller=None):
        target = controller or self.controller
        original_time = __import__("time").time
        __import__("time").time = lambda: now
        try:
            return asyncio.run(
                target.tick(
                    voltage=14.8,
                    current=current,
                    temp_ext=23.0,
                    is_cv=is_cv,
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
        self.assertEqual(self.controller.antisulfate_count, 1)
        self.assertIn("notify", actions)
        self.assertIn("десульфатация", actions["notify"].lower())

    def test_mix_hold_resets_on_new_minimum_even_without_cv_flag(self):
        points = [
            (301.0, 0.29, True),
            (3901.0, 0.28, False),
            (7201.0, 0.28, False),
            (12001.0, 0.28, False),
        ]

        actions = {}
        for now, current, is_cv in points:
            actions = self._tick(now=now, current=current, is_cv=is_cv)

        self.assertEqual(self.controller.current_stage, ChargeController.STAGE_MAIN)
        self.assertAlmostEqual(self.controller._first_stage_hold_current, 0.28)
        self.assertAlmostEqual(self.controller._first_stage_hold_since, 3901.0)
        self.assertNotIn("turn_off", actions)

    def test_agm_hold_resets_on_new_minimum_even_without_cv_flag(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_AGM, 60)
        controller.current_stage = ChargeController.STAGE_MAIN
        controller.stage_start_time = 0.0
        controller.total_start_time = 0.0

        points = [
            (301.0, 0.19, True),
            (3901.0, 0.18, False),
            (7201.0, 0.18, False),
        ]

        actions = {}
        for now, current, is_cv in points:
            actions = self._tick(now=now, current=current, is_cv=is_cv, controller=controller)

        self.assertEqual(controller.current_stage, ChargeController.STAGE_MAIN)
        self.assertAlmostEqual(controller._first_stage_hold_current, 0.18)
        self.assertAlmostEqual(controller._first_stage_hold_since, 3901.0)
        self.assertNotIn("turn_off", actions)


if __name__ == "__main__":
    unittest.main()
