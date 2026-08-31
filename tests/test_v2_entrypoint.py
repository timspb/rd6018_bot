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

    def test_final_semantic_operator_hmi_is_installed(self):
        self.assertTrue(bot._operator_hmi_installed)
        self.assertTrue(bot._operator_graph_dashboard_installed)
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

        # The semantic layer owns caption/button meaning, while production deliberately
        # keeps the graph/photo transport rather than switching L2 to a text-only card.
        self.assertEqual(
            bot._build_and_send_dashboard.__name__,
            "build_and_send_graph_dashboard",
        )
        self.assertEqual(bot._compact_dashboard_caption.__name__, "compact_dashboard_caption")

        # Production import has no live hardware state. Its durable ownership state is
        # allowed to affect the exact main-panel branch, but the final renderer must no
        # longer expose the old graph-range/developer button carpet. The graph itself
        # remains in the dashboard media and ranges live in the graph workspace.
        dashboard = bot._build_dashboard_keyboard(False, 1)
        dashboard_callbacks = {
            button.callback_data
            for row in dashboard.inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertNotIn("chart_30m", dashboard_callbacks)
        self.assertNotIn("chart_2h", dashboard_callbacks)
        self.assertNotIn("chart_session", dashboard_callbacks)
        self.assertNotIn("v2_status", dashboard_callbacks)
        self.assertNotIn("entities_status", dashboard_callbacks)
        self.assertIn("operator_graph", dashboard_callbacks)
        self.assertIn("operator_more", dashboard_callbacks)

    def test_charge_mode_copy_matches_normal_full_auto_contract(self):
        text = bot._charge_modes_text()
        self.assertIn("Обычный — штатный полный автоматический заряд", text)
        self.assertIn("recovery/Mix выполняются только по критериям", text)
        self.assertNotIn("без автоматического HV/Mix", text)

    def test_active_managed_dashboard_keeps_hard_stop_callback(self):
        # Temporarily present a normal managed session to the final semantic keyboard.
        manager = bot.rd_control_mode_manager
        controller = bot.charge_controller
        old_mode = manager.mode
        old_stage = controller.current_stage
        old_profile = controller.battery_type
        old_capacity = controller.ah_capacity
        try:
            from rd_control_mode import RdControlMode

            manager.mode = RdControlMode.PB_MANAGED
            controller.current_stage = controller.STAGE_MAIN
            controller.battery_type = controller.PROFILE_CA
            controller.ah_capacity = 72
            # is_active is a property derived from the stage.
            dashboard = bot._build_dashboard_keyboard(True, 1)
            callbacks = {
                button.callback_data
                for row in dashboard.inline_keyboard
                for button in row
                if button.callback_data
            }
            self.assertIn("power_toggle", callbacks)
            self.assertIn("operator_details", callbacks)
            self.assertIn("operator_graph", callbacks)
        finally:
            manager.mode = old_mode
            controller.current_stage = old_stage
            controller.battery_type = old_profile
            controller.ah_capacity = old_capacity

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
