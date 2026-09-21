import unittest

import v2_bot_ui
from pb_domain import BatteryCondition, ChargeIntent
from v2_bot_ui import PendingStart


class ModeSelectionRuntimeTests(unittest.TestCase):
    def tearDown(self):
        v2_bot_ui._pending_profile.clear()
        v2_bot_ui._pending_start.clear()
        v2_bot_ui._selected_battery.clear()

    def test_profile_selection_is_visible_before_capacity(self):
        v2_bot_ui._pending_profile[42] = "AGM"
        self.assertEqual(
            v2_bot_ui.selected_program_for_user(42),
            "AGM · ожидается ёмкость АКБ",
        )

    def test_pending_program_replaces_profile_preview(self):
        v2_bot_ui._pending_profile[42] = "Ca/Ca"
        v2_bot_ui._pending_start[42] = PendingStart(
            profile="EFB",
            capacity_ah=70,
            intent=ChargeIntent.NORMAL,
            battery_id="battery-70",
            condition=BatteryCondition.UNKNOWN,
        )
        self.assertEqual(
            v2_bot_ui.selected_program_for_user(42),
            "EFB 70 Ah · Обычный заряд",
        )

    def test_no_selection_does_not_relabel_readback(self):
        self.assertIsNone(v2_bot_ui.selected_program_for_user(42))


if __name__ == "__main__":
    unittest.main()
