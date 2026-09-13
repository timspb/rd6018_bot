import os
import unittest

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot
import operator_dashboard
import operator_hmi as hmi
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

    def _state(self, process_state, authority, *, output_on=False):
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

        self.assertEqual(
            bot._build_and_send_dashboard.__name__,
            "build_and_send_graph_dashboard",
        )
        self.assertEqual(bot._compact_dashboard_caption.__name__, "compact_dashboard_caption")

        # V1 compatibility lives only on the truthful graph/dashboard path.  Do not
        # decorate the legacy bool-only _build_dashboard_keyboard surface: it cannot
        # distinguish confirmed OFF from stale/UNKNOWN Output.
        state = self._state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE)
        dashboard = operator_dashboard._main_graph_markup(bot, state, 1)
        rows = dashboard.inline_keyboard
        dashboard_callbacks = {
            button.callback_data
            for row in rows
            for button in row
            if button.callback_data
        }
        dashboard_texts = {button.text for row in rows for button in row}

        self.assertEqual(
            [button.callback_data for button in rows[0]],
            ["operator_graph_30m", "operator_graph_2h", "operator_graph_session"],
        )
        self.assertNotIn("power_toggle", dashboard_callbacks)
        self.assertIn("v2_batteries", dashboard_callbacks)
        self.assertIn("charge_modes", dashboard_callbacks)
        self.assertIn("operator_more", dashboard_callbacks)
        self.assertIn("🚀 СТАРТ", dashboard_texts)
        self.assertIn("⚙️ Режимы", dashboard_texts)
        self.assertIn("🔄 Обновить", dashboard_texts)
        self.assertIn("📋 Полная инфо", dashboard_texts)
        self.assertIn("📝 Логи", dashboard_texts)
        self.assertIn("🧠 AI анализ", dashboard_texts)
        self.assertIn("🛠 Ещё", dashboard_texts)

    def test_charge_mode_copy_matches_normal_full_auto_contract(self):
        text = bot._charge_modes_text()
        self.assertIn("Обычный — штатный полный автоматический заряд", text)
        self.assertIn("recovery/Mix выполняются только по критериям", text)
        self.assertNotIn("без автоматического HV/Mix", text)

    def test_active_managed_graph_dashboard_uses_session_bound_stop_not_legacy_toggle(self):
        manager = bot.rd_control_mode_manager
        old_mode = manager.mode
        try:
            from rd_control_mode import RdControlMode

            manager.mode = RdControlMode.PB_MANAGED
            state = self._state(
                hmi.HmiProcessState.RUNNING,
                hmi.HmiAuthority.AUTO,
                output_on=True,
            )
            dashboard = operator_dashboard._main_graph_markup(bot, state, 1)
            callbacks = {
                button.callback_data
                for row in dashboard.inline_keyboard
                for button in row
                if button.callback_data
            }
            self.assertIn("operator_managed_stop", callbacks)
            self.assertNotIn("power_toggle", callbacks)
            self.assertIn("operator_details", callbacks)
            self.assertIn("operator_more", callbacks)
        finally:
            manager.mode = old_mode

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
