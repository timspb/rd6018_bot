import unittest

from charge_logic import ChargeController


class _FakeHass:
    pass


class MixDeltaModeTests(unittest.TestCase):
    def test_voltage_delta_requires_confirmed_cc(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 72)
        controller.current_stage = ChargeController.STAGE_MIX
        controller.v_max_recorded = 16.55
        controller.i_min_recorded = 1.50

        self.assertFalse(
            controller._check_delta_finish(
                16.51, 1.81, is_cv=False, is_cc=False
            )
        )
        self.assertTrue(
            controller._check_delta_finish(
                16.51, 1.81, is_cv=False, is_cc=True
            )
        )

    def test_current_delta_requires_confirmed_cv(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 72)
        controller.current_stage = ChargeController.STAGE_MIX
        controller.v_max_recorded = 16.55
        controller.i_min_recorded = 1.50

        self.assertFalse(
            controller._check_delta_finish(
                16.55, 1.95, is_cv=False, is_cc=False
            )
        )
        self.assertTrue(
            controller._check_delta_finish(
                16.55, 1.95, is_cv=True, is_cc=False
            )
        )

    def test_temperature_compensation_step_does_not_fake_voltage_delta(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 72)
        controller.current_stage = ChargeController.STAGE_MIX
        controller.v_max_recorded = 16.55
        controller.v_max_normalized_recorded = 0.01
        controller._current_normalized_voltage = 0.00

        # Raw voltage fell by 0.09 V only because the compensated target moved.
        self.assertFalse(
            controller._check_delta_finish(
                16.46, 1.70, is_cv=False, is_cc=True
            )
        )

    def test_real_normalized_voltage_delta_finishes_cc(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_CA, 72)
        controller.current_stage = ChargeController.STAGE_MIX
        controller.v_max_recorded = 16.55
        controller.v_max_normalized_recorded = 0.01
        controller._current_normalized_voltage = -0.04

        self.assertTrue(
            controller._check_delta_finish(
                16.42, 1.70, is_cv=False, is_cc=True
            )
        )


if __name__ == "__main__":
    unittest.main()
