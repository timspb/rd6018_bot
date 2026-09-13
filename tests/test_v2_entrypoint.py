import os
import unittest

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot
import operator_dashboard
import operator_hmi as hmi
from diagnostic_persistence import DiagnosticActionJournal
from operator_output_truth import OUTPUT_TRUTH_ATTR
from production_controller import ProductionChargeControllerV2


class V2EntrypointTests(unittest.TestCase):
    @staticmethod
    def _callbacks(markup):
        return {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }

    @staticmethod
    def _state(process_state, authority, *, output_on=False):
        return hmi.OperatorHmiState(
            process_state=process_state,
            authority=authority,
            title="",
            output_on=output_on,
            regulator="—",
            battery_label="",
            battery_voltage_v=None,
            current_a=None,
            power_w=None,
            battery_temp_c=None,
            psu_temp_c=None,
            target_voltage_v=None,
            current_limit_a=None,
            progress="",
            safety="",
        )

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

        # The legacy boolean keyboard helper remains a semantic compatibility surface.
        # The V1 visual shell is composed only on the live graph/dashboard path where
        # Output freshness and ownership state have already been resolved.
        dashboard = bot._build_dashboard_keyboard(False, 1)
        dashboard_callbacks = self._callbacks(dashboard)
        self.assertNotIn("power_toggle", dashboard_callbacks)
        self.assertIn("v2_batteries", dashboard_callbacks)
        self.assertIn("charge_modes", dashboard_callbacks)
        self.assertNotIn("operator_more", dashboard_callbacks)

    def test_composed_graph_unknown_output_never_restores_v1_start(self):
        state = self._state(
            hmi.HmiProcessState.CONTAINMENT,
            hmi.HmiAuthority.CONTAINMENT,
            output_on=False,
        )
        object.__setattr__(state, OUTPUT_TRUTH_ATTR, False)

        markup = operator_dashboard._main_graph_markup(bot, state, 1)
        callbacks = self._callbacks(markup)

        self.assertIn("operator_graph_30m", callbacks)
        self.assertIn("operator_graph_2h", callbacks)
        self.assertIn("operator_graph_session", callbacks)
        self.assertIn("rd_ownership_output_off", callbacks)
        self.assertIn("operator_refresh", callbacks)
        self.assertIn("operator_details", callbacks)
        self.assertIn("logs", callbacks)
        self.assertIn("ai_analysis", callbacks)
        self.assertNotIn("v2_batteries", callbacks)
        self.assertNotIn("charge_modes", callbacks)
        self.assertNotIn("operator_more", callbacks)
        self.assertNotIn("power_toggle", callbacks)

    def test_composed_graph_autonomous_never_restores_pb_start(self):
        manager = bot.rd_control_mode_manager
        old_mode = manager.mode
        old_edge_autonomous = manager._edge_autonomous
        try:
            from rd_control_mode import RdControlMode

            manager.mode = RdControlMode.HANDS_OFF
            manager._edge_autonomous = True
            state = self._state(
                hmi.HmiProcessState.HANDS_OFF,
                hmi.HmiAuthority.EXTERNAL,
                output_on=False,
            )

            markup = operator_dashboard._main_graph_markup(bot, state, 1)
            callbacks = self._callbacks(markup)

            self.assertIn("operator_graph_30m", callbacks)
            self.assertIn("operator_graph_2h", callbacks)
            self.assertIn("operator_graph_session", callbacks)
            self.assertIn("rd_autonomous_exit", callbacks)
            self.assertIn("operator_refresh", callbacks)
            self.assertIn("operator_details", callbacks)
            self.assertIn("logs", callbacks)
            self.assertIn("ai_analysis", callbacks)
            self.assertNotIn("rd_hands_off_disable", callbacks)
            self.assertNotIn("rd_hands_off_output_off", callbacks)
            self.assertNotIn("rd_live_mix", callbacks)
            self.assertNotIn("v2_batteries", callbacks)
            self.assertNotIn("charge_modes", callbacks)
            self.assertNotIn("operator_more", callbacks)
            self.assertNotIn("power_toggle", callbacks)
        finally:
            manager.mode = old_mode
            manager._edge_autonomous = old_edge_autonomous

    def test_charge_mode_copy_matches_normal_full_auto_contract(self):
        text = bot._charge_modes_text()
        self.assertIn("Обычный — штатный полный автоматический заряд", text)
        self.assertIn("recovery/Mix выполняются только по критериям", text)
        self.assertNotIn("без автоматического HV/Mix", text)

    def test_active_managed_dashboard_uses_session_bound_stop_not_legacy_toggle(self):
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
            self.assertIn("operator_managed_stop", callbacks)
            self.assertNotIn("power_toggle", callbacks)
            self.assertIn("operator_details", callbacks)
            self.assertNotIn("operator_graph", callbacks)
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
