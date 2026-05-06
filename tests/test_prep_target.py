import unittest

from charge_logic import ChargeController


class _FakeHass:
    pass


class PrepTargetTests(unittest.TestCase):
    def test_prep_target_uses_one_percent_of_capacity(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_AGM, 70)

        voltage, current = controller._prep_target()

        self.assertAlmostEqual(voltage, 12.0)
        self.assertAlmostEqual(current, 0.7)

    def test_prep_target_keeps_floor_for_small_capacity(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 5)

        voltage, current = controller._prep_target()

        self.assertAlmostEqual(voltage, 12.0)
        self.assertAlmostEqual(current, 0.1)


if __name__ == "__main__":
    unittest.main()
