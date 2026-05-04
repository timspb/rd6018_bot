import asyncio
import unittest
from unittest.mock import patch

from charge_logic import AGM_STAGES, AGM_FIRST_STAGE_HOLD_SEC, ChargeController


class _FakeHass:
    pass


class MixLimitTests(unittest.TestCase):
    def test_agm_mix_entry_sets_new_ovp_ocp(self):
        messages = []
        controller = ChargeController(_FakeHass(), notify_cb=messages.append)
        controller.start(ChargeController.PROFILE_AGM, 70)
        controller.current_stage = ChargeController.STAGE_MAIN
        controller._agm_stage_idx = len(AGM_STAGES) - 1
        controller.stage_start_time = 0.0
        controller._first_stage_hold_since = 1000.0 - AGM_FIRST_STAGE_HOLD_SEC
        controller._first_stage_hold_current = 0.15
        controller._blanking_until = 0.0
        controller._delta_monitor_after = 0.0
        controller._last_known_output_on = True

        with patch("charge_logic.time.time", return_value=1000.0):
            actions = asyncio.run(
                controller.tick(
                    voltage=15.0,
                    current=0.15,
                    temp_ext=25.0,
                    is_cv=True,
                    ah=8.0,
                    output_is_on=True,
                )
            )

        self.assertEqual(controller.current_stage, ChargeController.STAGE_MIX)
        self.assertAlmostEqual(actions["set_voltage"], 16.3)
        self.assertAlmostEqual(actions["set_current"], 2.1)
        self.assertAlmostEqual(actions["set_ovp"], 16.4)
        self.assertAlmostEqual(actions["set_ocp"], 2.2)
        self.assertTrue(messages)


if __name__ == "__main__":
    unittest.main()
