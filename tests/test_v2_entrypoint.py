import os
import unittest

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot
from diagnostic_persistence import DiagnosticActionJournal
from production_controller import ProductionChargeControllerV2


class V2EntrypointTests(unittest.TestCase):
    def test_import_bot_exposes_preserved_runtime_with_production_controller(self):
        self.assertEqual(bot.__name__, "bot_legacy")
        self.assertIsInstance(bot.charge_controller, ProductionChargeControllerV2)

    def test_production_guardrails_are_installed_after_controller_composition(self):
        self.assertTrue(bot._v2_production_guardrails_installed)
        self.assertTrue(bot._v2_vin_psu_health_only)
        self.assertEqual(bot.MIN_INPUT_VOLTAGE, float("-inf"))
        self.assertTrue(bot.charge_controller._v2_production_cooling_guard_installed)

    def test_v2_dashboard_and_mode_adapters_are_installed(self):
        keyboard = bot._build_charge_modes_keyboard()
        callbacks = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("v2_profile_agm", callbacks)
        self.assertIn("v2_batteries", callbacks)
        self.assertIn("v2_mix", callbacks)
        self.assertIn("v2_manual_choose", callbacks)

        dashboard = bot._build_dashboard_keyboard(False, 1)
        dashboard_callbacks = {
            button.callback_data
            for row in dashboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("v2_status", dashboard_callbacks)
        self.assertIn("v2_batteries", dashboard_callbacks)
        self.assertIn("charge_modes", dashboard_callbacks)
        self.assertNotIn("power_toggle", dashboard_callbacks)

    def test_charge_mode_copy_matches_normal_full_auto_contract(self):
        text = bot._charge_modes_text()
        self.assertIn("Обычный — штатный полный автоматический заряд", text)
        self.assertIn("recovery/Mix выполняются только по критериям", text)
        self.assertNotIn("без автоматического HV/Mix", text)

    def test_active_dashboard_keeps_hard_stop_callback(self):
        dashboard = bot._build_dashboard_keyboard(True, 1)
        callbacks = {
            button.callback_data
            for row in dashboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("power_toggle", callbacks)

    def test_saved_battery_start_route_precedes_generic_battery_selector(self):
        handlers = bot.router.observers["callback_query"].handlers
        callback_names = [handler.callback.__name__ for handler in handlers]
        self.assertIn("_v2_battery_start_route", callback_names)
        self.assertIn("battery_select_handler", callback_names)
        self.assertLess(
            callback_names.index("_v2_battery_start_route"),
            callback_names.index("battery_select_handler"),
            "v2_battery_start must not be swallowed by the generic v2_battery_* selector",
        )

    def test_diagnostic_action_journal_is_installed(self):
        self.assertIsInstance(bot.diagnostic_action_journal, DiagnosticActionJournal)
        self.assertTrue(hasattr(bot, "controlled_diagnostic_probe"))


if __name__ == "__main__":
    unittest.main()
