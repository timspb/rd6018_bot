import pathlib
import unittest

import bot
import bot_legacy
import v2_bot_ui
import v2_startup


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class StartRouteIsolationTests(unittest.TestCase):
    def test_production_profile_start_has_one_transactional_owner(self):
        self.assertIs(v2_bot_ui._start_profile, v2_startup.start_profile_transactional)

        handlers = bot.router.observers["callback_query"].handlers
        names = [handler.callback.__name__ for handler in handlers]
        self.assertEqual(names.count("_v2_battery_start_route"), 1)

    def test_production_charge_modes_do_not_expose_legacy_profile_callbacks(self):
        callbacks = _callbacks(bot._build_charge_modes_keyboard())

        self.assertIn("v2_profile_caca", callbacks)
        self.assertIn("v2_profile_efb", callbacks)
        self.assertIn("v2_profile_agm", callbacks)
        self.assertNotIn("profile_caca", callbacks)
        self.assertNotIn("profile_efb", callbacks)
        self.assertNotIn("profile_agm", callbacks)
        self.assertNotIn("profile_custom", callbacks)

    def test_legacy_start_functions_remain_available_only_as_preserved_surface(self):
        # The rollback module remains importable, but its direct start functions are
        # not the production route asserted above.
        self.assertTrue(callable(bot_legacy.handle_ah_input))
        self.assertTrue(callable(bot_legacy.start_custom_charge))
        self.assertIsNot(bot_legacy.handle_ah_input, v2_bot_ui._start_profile)

    def test_quick_start_callback_uses_v3_route_when_composed(self):
        source = (pathlib.Path(__file__).parents[1] / "v2_bot_ui.py").read_text(encoding="utf-8")
        start = source.index('F.data == "v2_quick_start"')
        end = source.index('F.data.startswith("v2_bat_intent_")', start)
        callback = source[start:end]
        self.assertIn("_v3_production_start_route", callback)
        self.assertIn("await route.submit(intent)", callback)
        self.assertNotIn("app.charge_controller.start(", callback)
        self.assertNotIn("app.hass.turn_on(", callback)

    def test_legacy_capacity_input_uses_v3_route_when_composed(self):
        source = (pathlib.Path(__file__).parents[1] / "bot_legacy.py").read_text(encoding="utf-8")
        start = source.index("async def handle_ah_input")
        end = source.index("async def handle_dialog_mode", start)
        callback = source[start:end]
        self.assertIn("_v3_production_start_route", callback)
        self.assertIn("await route.submit(intent)", callback)
        self.assertIn("BatteryCondition.UNKNOWN", callback)


if __name__ == "__main__":
    unittest.main()
