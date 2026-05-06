import asyncio
import unittest
from unittest.mock import patch

from charge_logic import DESULF_OCP_MARGIN, ChargeController


class _FakeHass:
    pass


class DesulfLimitTests(unittest.TestCase):
    def test_agm_desulfation_uses_wider_ocp_margin(self):
        controller = ChargeController(_FakeHass())
        controller.start(ChargeController.PROFILE_AGM, 80)
        controller.current_stage = ChargeController.STAGE_MAIN
        controller.stage_start_time = 0.0
        controller._blanking_until = 0.0
        controller._last_known_output_on = True
        controller._stuck_current_since = 0.0
        controller._stuck_current_value = 1.60
        controller.antisulfate_count = 0

        with patch("charge_logic.time.time", return_value=7200.0):
            actions = asyncio.run(
                controller.tick(
                    voltage=14.8,
                    current=1.60,
                    temp_ext=25.0,
                    is_cv=True,
                    ah=10.0,
                    output_is_on=True,
                )
            )

        self.assertEqual(controller.current_stage, ChargeController.STAGE_DESULFATION)
        self.assertAlmostEqual(actions["set_voltage"], 16.3)
        self.assertAlmostEqual(actions["set_current"], 1.6)
        self.assertAlmostEqual(actions["set_ovp"], 16.4)
        self.assertAlmostEqual(actions["set_ocp"], 1.6 + DESULF_OCP_MARGIN)


if __name__ == "__main__":
    unittest.main()
