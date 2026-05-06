import os
import unittest
from unittest.mock import PropertyMock, patch

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abc")

import bot


class DashboardResilienceTests(unittest.TestCase):
    def test_stage_progress_line_survives_snapshot_failure(self):
        live = {
            "battery_voltage": 16.31,
            "current": 1.37,
            "temp_ext": 23.0,
            "is_cv": "on",
            "is_cc": "off",
        }

        controller = bot.charge_controller
        original_stage = controller.current_stage
        original_profile = controller.battery_type
        original_finish_timer = controller.finish_timer_start
        original_i_min = controller.i_min_recorded

        try:
            with patch.object(type(controller), "is_active", new_callable=PropertyMock, return_value=True):
                controller.current_stage = controller.STAGE_MIX
                controller.battery_type = controller.PROFILE_AGM
                controller.finish_timer_start = None
                controller.i_min_recorded = 1.0

                with patch.object(controller, "get_ai_stage_snapshot", side_effect=RuntimeError("boom")):
                    line = bot._format_stage_progress_line(live)

            self.assertIsInstance(line, str)
        finally:
            controller.current_stage = original_stage
            controller.battery_type = original_profile
            controller.finish_timer_start = original_finish_timer
            controller.i_min_recorded = original_i_min


if __name__ == "__main__":
    unittest.main()
