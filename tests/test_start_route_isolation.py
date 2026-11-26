import pathlib
import unittest

import bot  # compose production runtime
from runtime import production_runtime as runtime_app
import production_bot_ui
from types import SimpleNamespace


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class StartRouteIsolationTests(unittest.TestCase):
    def test_battery_start_callback_uses_captured_composed_route(self):
        source = (pathlib.Path(__file__).parents[1] / "production_bootstrap.py").read_text(encoding="utf-8")
        start = source.index('F.data == "v2_battery_start"')
        end = source.index("    install_ui_support(", start)
        callback = source[start:end]
        composition = source[:start]
        self.assertIn("battery_start_route = app._v3_production_start_route", composition)
        self.assertIn("await battery_start_route.submit(intent)", callback)
        self.assertNotIn("app._v3_production_start_route", callback)

    def test_start_feedback_reports_active_execution_result(self):
        result = SimpleNamespace(
            accepted=True,
            trace_id="trace-active-1234",
            reason="started",
            port_result=SimpleNamespace(
                mode=SimpleNamespace(value="active"),
                execution_result=SimpleNamespace(status=SimpleNamespace(value="STARTED")),
            ),
        )
        feedback = production_bot_ui.format_start_feedback(result)
        self.assertIn("ACTIVE START STARTED", feedback)
        self.assertNotIn("DRY_RUN", feedback)

    def test_start_feedback_preserves_explicit_dry_run(self):
        result = SimpleNamespace(
            accepted=True,
            trace_id="trace-dry-1234",
            reason="dry_run_routed_no_mutation",
            port_result=SimpleNamespace(
                mode=SimpleNamespace(value="dry_run"),
                execution_result=None,
            ),
        )
        feedback = production_bot_ui.format_start_feedback(result)
        self.assertIn("DRY_RUN", feedback)
        self.assertIn("не запускался", feedback)

    def test_start_feedback_is_owned_by_pure_hmi_component(self):
        from runtime.ui.components.hmi_values import format_start_feedback
        self.assertIs(production_bot_ui.format_start_feedback, format_start_feedback)

    def test_start_feedback_consumes_typed_read_only_route_result(self):
        from runtime.ui.components.hmi_values import StartFeedbackResult, format_start_feedback
        from typing import Protocol
        self.assertEqual(format_start_feedback.__annotations__["result"], "StartFeedbackResult")
        self.assertIn(Protocol, StartFeedbackResult.__bases__)

    def test_start_feedback_contract_flows_through_telegram_injections(self):
        from typing import get_args, get_type_hints
        from runtime.ui.components.hmi_values import StartFeedbackResult
        from runtime.ui.telegram import charge

        feedback_contracts = (
            (charge.handle_capacity_input, "format_start_feedback"),
        )
        for function, parameter in feedback_contracts:
            with self.subTest(function=function.__name__):
                annotation = get_type_hints(function)[parameter]
                self.assertIs(get_args(annotation)[0][0], StartFeedbackResult)

    def test_start_feedback_rejection_and_unknown_mode_are_truthful(self):
        from runtime.ui.components.hmi_values import format_start_feedback
        rejected = SimpleNamespace(accepted=False, trace_id="trace", reason="lease_not_ready")
        self.assertEqual(format_start_feedback(rejected), "START отклонён: lease_not_ready")
        accepted = SimpleNamespace(
            accepted=True, trace_id="abcd1234long", reason="accepted",
            port_result=SimpleNamespace(mode=SimpleNamespace(value="queued")),
        )
        self.assertEqual(format_start_feedback(accepted), "✅ START QUEUED: accepted (abcd1234)")

    def test_production_profile_start_has_one_transactional_owner(self):
        self.assertFalse(hasattr(production_bot_ui, "_start_profile"))

        handlers = runtime_app.router.observers["callback_query"].handlers
        names = [handler.callback.__name__ for handler in handlers]
        self.assertEqual(names.count("_battery_start_route"), 1)

    def test_production_start_graph_has_no_legacy_runner_or_owner_import(self):
        root = pathlib.Path(__file__).parents[1]
        for rel in (
            "production_bootstrap.py",
            "application/start_transaction_runner.py",
        ):
            source = (root / rel).read_text(encoding="utf-8")
            self.assertNotIn("from v2_startup import", source, rel)
            self.assertNotIn("V2StartRunnerAdapter", source, rel)
        self.assertIn(
            "StartTransactionRunner",
            (root / "production_bootstrap.py").read_text(encoding="utf-8"),
        )
        bootstrap = (root / "production_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("StartTransactionRunner", bootstrap)
        self.assertIn("ProductionStartRouteAdapter", bootstrap)

    def test_production_charge_modes_do_not_expose_legacy_profile_callbacks(self):
        callbacks = _callbacks(runtime_app._build_charge_modes_keyboard())

        self.assertIn("v2_profile_caca", callbacks)
        self.assertIn("v2_profile_efb", callbacks)
        self.assertIn("v2_profile_agm", callbacks)
        self.assertNotIn("profile_caca", callbacks)
        self.assertNotIn("profile_efb", callbacks)
        self.assertNotIn("profile_agm", callbacks)
        self.assertNotIn("profile_custom", callbacks)

    def test_retired_start_facades_are_absent(self):
        root = pathlib.Path(__file__).parents[1]
        self.assertFalse((root / "bot_legacy.py").exists())
        self.assertFalse((root / "v2_startup.py").exists())
        self.assertFalse((root / "application" / "v2_start_runner_adapter.py").exists())

    def test_composed_custom_dialog_uses_typed_manual_route(self):
        self.assertIs(runtime_app.manual_ui_route.manager, runtime_app.manual_session_manager)
        self.assertFalse(hasattr(runtime_app, "start_custom_charge"))
        self.assertFalse(hasattr(runtime_app.manual_session_manager, "start_from_legacy_ui"))

    def test_quick_start_callback_uses_v3_route_when_composed(self):
        source = (pathlib.Path(__file__).parents[1] / "production_bot_ui.py").read_text(encoding="utf-8")
        start = source.index('F.data == "v2_quick_start"')
        end = source.index('F.data.startswith("v2_bat_intent_")', start)
        callback = source[start:end]
        self.assertIn("production_start_route", callback)
        composition = (pathlib.Path(__file__).parents[1] / "production_bot_ui.py").read_text(encoding="utf-8")
        self.assertIn("start_route=app._v3_production_start_route",
                      (pathlib.Path(__file__).parents[1] / "production_bootstrap.py").read_text(encoding="utf-8"))
        self.assertIn("production_start_route = (", composition)
        self.assertNotIn("_start_profile", callback)
        self.assertNotIn("Compatibility/rollback compositions", callback)
        self.assertIn("await route.submit(intent)", callback)
        self.assertNotIn("app.charge_controller.start(", callback)
        self.assertNotIn("app.hass.turn_on(", callback)
        submitted = callback.index("await route.submit(intent)")
        self.assertNotIn("await call.answer(", callback[submitted:])
        self.assertIn("message.answer(format_start_feedback(result), parse_mode=None)", callback)
        self.assertNotIn("await dashboard_builder(", callback)
        self.assertNotIn("_refresh_dashboard_after_selection", callback)

    def test_legacy_capacity_input_uses_v3_route_when_composed(self):
        root = pathlib.Path(__file__).parents[1]
        source = (root / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        start = source.index("async def handle_ah_input")
        end = source.index("async def handle_dialog_mode", start)
        adapter = source[start:end]
        self.assertIn('globals().get("_v3_production_start_route")', adapter)
        self.assertIn("await handle_capacity_input(", adapter)
        self.assertIn("route=route", adapter)
        self.assertNotIn("route.submit(", adapter)

        owner_source = (root / "runtime" / "ui" / "telegram" / "charge.py").read_text(encoding="utf-8")
        owner_start = owner_source.index("async def handle_capacity_input")
        owner_end = owner_source.index("CHARGE_CALLBACK_DATA", owner_start)
        owner = owner_source[owner_start:owner_end]
        self.assertIn("await route.submit(intent)", owner)
        self.assertIn("BatteryCondition.UNKNOWN", owner)
        self.assertIn("direct legacy START is retired", owner)
        for forbidden in (
            "charge_controller.start(",
            "hass.set_ovp(",
            "hass.set_ocp(",
            "hass.set_voltage(",
            "hass.set_current(",
            "hass.turn_on(",
        ):
            self.assertNotIn(forbidden, adapter + owner)


if __name__ == "__main__":
    unittest.main()
