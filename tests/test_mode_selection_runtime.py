import unittest

import production_bot_ui
from runtime.ui.telegram import charge as charge_ui
from runtime.ui.telegram import battery_selection
from battery_registry import BatteryRecord
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)
from production_bot_ui import PendingStart


class ModeSelectionRuntimeTests(unittest.TestCase):
    def tearDown(self):
        production_bot_ui._pending_profile.clear()
        production_bot_ui._pending_intent.clear()
        production_bot_ui._pending_start.clear()
        production_bot_ui._selected_battery.clear()

    def test_profile_selection_is_visible_before_capacity(self):
        production_bot_ui._pending_profile[42] = "AGM"
        self.assertEqual(
            production_bot_ui.selected_program_for_user(42),
            "AGM · ожидается ёмкость АКБ",
        )

    def test_program_wizard_compatibility_exports_are_direct_owner_aliases(self):
        import manual_context
        self.assertIs(production_bot_ui.PendingStart, charge_ui.PendingStart)
        self.assertIs(production_bot_ui._pending_profile, charge_ui._pending_profile)
        self.assertIs(production_bot_ui._pending_intent, charge_ui._pending_intent)
        self.assertIs(production_bot_ui._pending_start, charge_ui._pending_start)
        self.assertIs(production_bot_ui.selected_program_for_user, charge_ui.selected_program_for_user)
        self.assertIs(production_bot_ui._clear_pending_program_state, charge_ui._clear_pending_program_state)
        self.assertIs(production_bot_ui._selected_battery, battery_selection._selected_battery)
        self.assertIs(manual_context.selected_battery_for_user, battery_selection.selected_battery_for_user)

    def test_program_projection_precedence_and_battery_fallback(self):
        user_id = 42
        production_bot_ui._selected_battery[user_id] = BatteryRecord(
            BatteryIdentity("efb-72", BatteryChemistry.EFB, 72),
            BatteryLifecycle(),
        )
        self.assertIn("выбрана АКБ", production_bot_ui.selected_program_for_user(user_id))
        production_bot_ui._pending_profile[user_id] = "AGM"
        self.assertEqual(
            production_bot_ui.selected_program_for_user(user_id),
            "AGM · ожидается ёмкость АКБ",
        )
        production_bot_ui._pending_start[user_id] = PendingStart(
            profile="EFB", capacity_ah=60, intent=ChargeIntent.NORMAL,
            battery_id="battery-60", condition=BatteryCondition.UNKNOWN,
        )
        self.assertEqual(
            production_bot_ui.selected_program_for_user(user_id),
            "EFB 60 Ah · Обычный заряд",
        )
        production_bot_ui._selected_battery.pop(user_id, None)

    def test_pending_program_replaces_profile_preview(self):
        production_bot_ui._pending_profile[42] = "Ca/Ca"
        production_bot_ui._pending_start[42] = PendingStart(
            profile="EFB",
            capacity_ah=70,
            intent=ChargeIntent.NORMAL,
            battery_id="battery-70",
            condition=BatteryCondition.UNKNOWN,
        )
        self.assertEqual(
            production_bot_ui.selected_program_for_user(42),
            "EFB 70 Ah · Обычный заряд",
        )

    def test_no_selection_does_not_relabel_readback(self):
        self.assertIsNone(production_bot_ui.selected_program_for_user(42))

    def test_accepted_start_clears_all_selection_wizard_state(self):
        app = type("App", (), {"awaiting_ah": {42: "AGM", 43: "EFB"}})()
        production_bot_ui._pending_profile[42] = "AGM"
        production_bot_ui._pending_intent[42] = ChargeIntent.RECOVERY
        production_bot_ui._pending_start[42] = PendingStart(
            profile="AGM",
            capacity_ah=90,
            intent=ChargeIntent.RECOVERY,
            battery_id="adhoc:AGM:90:42",
            condition=BatteryCondition.UNKNOWN,
        )
        production_bot_ui._pending_profile[43] = "EFB"
        production_bot_ui._pending_intent[43] = ChargeIntent.NORMAL

        production_bot_ui._clear_pending_program_state(app, 42)

        self.assertIsNone(production_bot_ui.selected_program_for_user(42))
        self.assertNotIn(42, app.awaiting_ah)
        self.assertEqual(production_bot_ui._pending_profile[43], "EFB")
        self.assertEqual(production_bot_ui._pending_intent[43], ChargeIntent.NORMAL)
        self.assertEqual(app.awaiting_ah[43], "EFB")
        production_bot_ui._pending_profile.pop(43, None)
        production_bot_ui._pending_intent.pop(43, None)


if __name__ == "__main__":
    unittest.main()
