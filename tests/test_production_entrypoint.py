import os
import unittest

os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

import bot
from runtime import production_runtime
import operator_dashboard
import operator_hmi as hmi
from diagnostic_persistence import DiagnosticActionJournal
from operator_output_truth import OUTPUT_TRUTH_ATTR
from production_controller import ProductionChargeController
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA


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

    def test_import_bot_is_distinct_composition_module_with_runtime_bridge(self):
        self.assertEqual(bot.__name__, "bot")
        self.assertIs(bot.charge_controller, production_runtime.charge_controller)
        self.assertIsInstance(bot.charge_controller, ProductionChargeController)

    def test_bot_no_longer_aliases_or_mutates_legacy_module_identity(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        self.assertNotIn("sys.modules[__name__]", source)
        self.assertNotIn("_legacy.main = main", source)
        self.assertNotIn("from runtime import v2_runtime", source)
        self.assertIn("from runtime import production_runtime as _runtime_substrate", source)
        self.assertNotIn("_legacy_main = _composition.", source)
        self.assertNotIn("_v2_startup_recovery = _composition.", source)
        self.assertIn("def __getattr__(name: str):", source)

    def test_production_composition_owns_all_installer_calls(self):
        import ast
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        top_level_calls = []
        for node in tree.body:
            value = None
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                value = node.value
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                value = node.value
            if value is not None:
                top_level_calls.append(ast.unparse(value))

        self.assertEqual(
            top_level_calls,
            ["ProductionComposition(_runtime_substrate).compose()"],
        )
        self.assertIsInstance(bot._composition, bot.ProductionComposition)
        self.assertTrue(bot._composition.composed)
        self.assertIs(bot._composition.runtime, production_runtime)

        install_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                (
                    isinstance(node.func, ast.Name)
                    and node.func.id.startswith("install_")
                )
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr.startswith("install_")
                )
            )
        ]
        self.assertTrue(install_calls)

        compose = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ProductionComposition"
        )
        compose_method = next(
            node
            for node in compose.body
            if isinstance(node, ast.FunctionDef) and node.name == "compose"
        )
        compose_call_ids = {id(node) for node in ast.walk(compose_method)}
        self.assertTrue(all(id(call) in compose_call_ids for call in install_calls))

    def test_production_lifecycle_is_owned_by_composition(self):
        import ast
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        composition = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ProductionComposition"
        )
        run_method = next(
            node
            for node in composition.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run"
        )
        main = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "main"
        )
        run_source = ast.get_source_segment(source, run_method) or ""
        main_source = ast.get_source_segment(source, main) or ""

        self.assertIn("_composition.run(", main_source)
        for forbidden in (
            "asyncio.create_task(",
            "reconcile_startup_authority(",
            "_physical_test_control.start(",
            "_physical_test_control.stop(",
            "_legacy_main()",
        ):
            self.assertNotIn(forbidden, main_source)

        for required in (
            "reconcile_startup_authority(",
            "await physical.start()",
            "await main_runner()",
            "await physical.stop()",
        ):
            self.assertIn(required, run_source)

    def test_production_guardrails_are_owned_without_composition_wrapper(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        self.assertNotIn("install_production_guardrails", source)
        self.assertNotIn("production_guardrails_v2", source)
        self.assertTrue(bot._v2_vin_psu_health_only)
        self.assertEqual(bot.MIN_INPUT_VOLTAGE, float("-inf"))
        self.assertFalse(hasattr(bot, "_v2_production_guardrails_installed"))
        self.assertFalse(
            hasattr(bot.charge_controller, "_v2_production_cooling_guard_installed")
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

        # The semantic layer owns caption/button meaning; routine L2 updates remain
        # text-only and the explicit graph workspace owns photo rendering.
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
        self.assertNotIn("v2_batteries", dashboard_callbacks)
        self.assertIn(CHARGE_CALLBACK_DATA, dashboard_callbacks)
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

        self.assertNotIn("operator_graph_30m", callbacks)
        self.assertNotIn("operator_graph_2h", callbacks)
        self.assertNotIn("operator_graph_session", callbacks)
        self.assertIn("rd_ownership_output_off", callbacks)
        self.assertIn("operator_refresh", callbacks)
        self.assertNotIn("operator_details", callbacks)
        self.assertNotIn("logs", callbacks)
        self.assertNotIn("ai_analysis", callbacks)
        self.assertNotIn("v2_batteries", callbacks)
        self.assertNotIn(CHARGE_CALLBACK_DATA, callbacks)
        self.assertNotIn("operator_more", callbacks)
        self.assertNotIn("power_toggle", callbacks)

    def test_root_uses_existing_rd_control_screen_composition(self):
        state = self._state(
            hmi.HmiProcessState.IDLE,
            hmi.HmiAuthority.NONE,
            output_on=False,
        )

        markup = operator_dashboard._main_graph_markup(bot, state, 1)
        callbacks = self._callbacks(markup)

        self.assertIn(CHARGE_CALLBACK_DATA, callbacks)
        self.assertIn("rd_ownership_hands_off", callbacks)
        self.assertIn("rd_autonomous_confirm", callbacks)
        self.assertIn("operator_refresh", callbacks)
        self.assertNotIn("operator_details", callbacks)
        self.assertNotIn("rd_hands_off_output_off", callbacks)
        self.assertNotIn("rd_hands_off_disable", callbacks)

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

            self.assertNotIn("operator_graph_30m", callbacks)
            self.assertNotIn("operator_graph_2h", callbacks)
            self.assertNotIn("operator_graph_session", callbacks)
            self.assertIn("rd_autonomous_exit", callbacks)
            self.assertIn("operator_refresh", callbacks)
            self.assertNotIn("operator_details", callbacks)
            self.assertNotIn("logs", callbacks)
            self.assertNotIn("ai_analysis", callbacks)
            self.assertNotIn("rd_hands_off_disable", callbacks)
            self.assertNotIn("rd_hands_off_output_off", callbacks)
            self.assertNotIn("rd_live_mix", callbacks)
            self.assertNotIn("v2_batteries", callbacks)
            self.assertNotIn(CHARGE_CALLBACK_DATA, callbacks)
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
            self.assertNotIn("operator_details", callbacks)
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
