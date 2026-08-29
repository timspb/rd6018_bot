import os
import unittest

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot
from production_controller import ProductionChargeControllerV2


class V2EntrypointTests(unittest.TestCase):
    def test_import_bot_exposes_preserved_runtime_with_production_controller(self):
        self.assertEqual(bot.__name__, "bot_legacy")
        self.assertIsInstance(bot.charge_controller, ProductionChargeControllerV2)

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

        dashboard = bot._build_dashboard_keyboard(False, 1)
        dashboard_callbacks = {
            button.callback_data
            for row in dashboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertIn("v2_status", dashboard_callbacks)
        self.assertIn("v2_batteries", dashboard_callbacks)


if __name__ == "__main__":
    unittest.main()
