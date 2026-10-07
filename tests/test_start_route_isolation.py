import pathlib
import unittest

import bot
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

    def test_production_profile_start_has_one_transactional_owner(self):
        from application.start_transaction_service import start_profile_transactional

        self.assertIs(production_bot_ui._start_profile, start_profile_transactional)

        handlers = bot.router.observers["callback_query"].handlers
        names = [handler.callback.__name__ for handler in handlers]
        self.assertEqual(names.count("_v2_battery_start_route"), 1)

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
        self.assertIn(
            "start_transaction_service",
            (root / "production_bootstrap.py").read_text(encoding="utf-8"),
        )

    def test_production_charge_modes_do_not_expose_legacy_profile_callbacks(self):
        callbacks = _callbacks(bot._build_charge_modes_keyboard())

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

    def test_composed_custom_dialog_is_bound_to_manual_session_owner(self):
        self.assertIs(bot.start_custom_charge.__self__, bot.manual_session_manager)
        self.assertIs(
            bot.start_custom_charge.__func__,
            bot.manual_session_manager.start_from_legacy_ui.__func__,
        )

    def test_quick_start_callback_uses_v3_route_when_composed(self):
        source = (pathlib.Path(__file__).parents[1] / "production_bot_ui.py").read_text(encoding="utf-8")
        start = source.index('F.data == "v2_quick_start"')
        end = source.index('F.data.startswith("v2_bat_intent_")', start)
        callback = source[start:end]
        self.assertIn("_v3_production_start_route", callback)
        self.assertIn("await route.submit(intent)", callback)
        self.assertNotIn("app.charge_controller.start(", callback)
        self.assertNotIn("app.hass.turn_on(", callback)
        submitted = callback.index("await route.submit(intent)")
        self.assertNotIn("await call.answer(", callback[submitted:])
        self.assertIn("message.answer(format_start_feedback(result), parse_mode=None)", callback)

    def test_legacy_capacity_input_uses_v3_route_when_composed(self):
        source = (pathlib.Path(__file__).parents[1] / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        start = source.index("async def handle_ah_input")
        end = source.index("async def handle_dialog_mode", start)
        callback = source[start:end]
        self.assertIn("_v3_production_start_route", callback)
        self.assertIn("await route.submit(intent)", callback)
        self.assertIn("BatteryCondition.UNKNOWN", callback)
        self.assertIn("direct legacy START is retired", callback)
        for forbidden in (
            "charge_controller.start(",
            "hass.set_ovp(",
            "hass.set_ocp(",
            "hass.set_voltage(",
            "hass.set_current(",
            "hass.turn_on(",
        ):
            self.assertNotIn(forbidden, callback)


if __name__ == "__main__":
    unittest.main()
