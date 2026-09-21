import asyncio
import unittest
from types import SimpleNamespace
from pathlib import Path

import bot
from application.intents import OperatorIntent, OperatorIntentKind
from application.production_start_route import ProductionStartRouteAdapter
from application.production_start_execution_port import ProductionStartMode
from application.production_start_runner import ProductionStartRunner
from application.v2_start_runner_adapter import V2StartRunnerAdapter
from application.start_request import StartRequest
from application.start_preflight import StartPreflightService
from application.start_plan import approved_plan_from_preflight
from pb_domain import BatteryChemistry, BatteryIdentity


class _Hass:
    async def get_all_live(self):
        return {
            "battery_voltage": 13.5,
            "current": 0.0,
            "temp_ext": 25.0,
            "temp_int": 30.0,
            "input_voltage": 60.0,
            "switch": "off",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "_freshness": {key: 0.0 for key in (
                "battery_voltage", "current", "temp_ext", "temp_int", "switch",
                "ovp_triggered", "ocp_triggered",
            )},
        }


class _Controller:
    is_active = False

    def _main_target(self, _temperature):
        return 14.4, 7.0

    def _prep_target(self, _temperature):
        return 12.0, 0.7


class _App:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    hass = _Hass()
    charge_controller = _Controller()
    rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


def _intent():
    return OperatorIntent(
        OperatorIntentKind.START_CHARGE,
        "telegram",
        "operator-1",
        {
            "profile": "AGM",
            "capacity_ah": 70,
            "battery_identity": BatteryIdentity("battery-1", BatteryChemistry.AGM, 70),
            "battery_id": "battery-1",
            "intent": StartRequest.__dataclass_fields__["intent"].default,
            "condition": StartRequest.__dataclass_fields__["condition"].default,
        },
    )


class ProductionStartRouteTests(unittest.TestCase):
    def test_production_composition_installs_one_active_route(self):
        self.assertIsInstance(bot._v3_production_start_route, ProductionStartRouteAdapter)
        self.assertEqual(bot._v3_production_start_route.mode, ProductionStartMode.ACTIVE)
        port = bot._v3_production_start_route.port
        self.assertIsInstance(port.production_runner, ProductionStartRunner)
        self.assertIsInstance(port.production_runner.transaction_runner, V2StartRunnerAdapter)

        source = Path("v2_bootstrap.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('F.data == "v2_battery_start"'), 1)
        self.assertNotIn("start_profile_transactional(app, call, pending)", source)

    def test_composed_dry_run_keeps_runner_boundary_non_actuating(self):
        composed_port = bot._v3_production_start_route.port
        result = asyncio.run(ProductionStartRouteAdapter(_App(), port=composed_port, mode=ProductionStartMode.DRY_RUN).submit(_intent()))
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "dry_run_routed_no_mutation")
        self.assertIsNotNone(composed_port.production_runner)

    def test_explicit_dry_run_preserves_trace(self):
        _App.rd_control_mode_manager.hands_off = False
        adapter = ProductionStartRouteAdapter(_App(), mode=ProductionStartMode.DRY_RUN)
        result = asyncio.run(adapter.submit(_intent()))
        self.assertTrue(result.accepted)
        self.assertEqual(adapter.mode, ProductionStartMode.DRY_RUN)
        self.assertEqual(result.port_result.reason, "dry_run_routed_no_mutation")
        self.assertEqual(result.port_result.request.trace_id, result.trace_id)

    def test_active_route_is_available_after_preflight(self):
        adapter = ProductionStartRouteAdapter(_App(), mode=ProductionStartMode.ACTIVE)
        self.assertEqual(adapter.mode, ProductionStartMode.ACTIVE)

    def test_denied_preflight_does_not_create_plan(self):
        app = _App()
        app.rd_control_mode_manager.hands_off = True
        result = asyncio.run(ProductionStartRouteAdapter(app).submit(_intent()))
        self.assertFalse(result.accepted)
        self.assertIsNone(result.plan)
        self.assertIn("preflight_denied:hands_off", result.reason)

    def test_missing_intent_is_denied_before_recipe_selection(self):
        values = dict(_intent().parameters)
        values.pop("intent")
        result = asyncio.run(
            ProductionStartRouteAdapter(_App()).submit(
                OperatorIntent(OperatorIntentKind.START_CHARGE, "telegram", "operator-1", values)
            )
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_start_intent")
        self.assertIsNone(result.plan)
        self.assertIsNone(result.port_result)

    def test_missing_condition_is_denied_before_recipe_selection(self):
        values = dict(_intent().parameters)
        values.pop("condition")
        result = asyncio.run(
            ProductionStartRouteAdapter(_App()).submit(
                OperatorIntent(OperatorIntentKind.START_CHARGE, "telegram", "operator-1", values)
            )
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "invalid_start_intent")
        self.assertIsNone(result.plan)
        self.assertIsNone(result.port_result)

    def test_invalid_profile_is_denied_without_plan(self):
        values = dict(_intent().parameters)
        values["profile"] = "NOT_A_PROFILE"
        _App.rd_control_mode_manager.hands_off = False
        result = asyncio.run(
            ProductionStartRouteAdapter(_App()).submit(
                OperatorIntent(OperatorIntentKind.START_CHARGE, "telegram", "operator-1", values)
            )
        )
        self.assertFalse(result.accepted)
        self.assertTrue(result.reason.startswith("preflight_denied:"))
        self.assertIn("invalid_profile", result.reason)
        self.assertIsNone(result.plan)

    def test_denied_start_keeps_trace_id_without_execution_result(self):
        values = dict(_intent().parameters)
        values.pop("intent")
        result = asyncio.run(
            ProductionStartRouteAdapter(_App()).submit(
                OperatorIntent(OperatorIntentKind.START_CHARGE, "telegram", "operator-1", values)
            )
        )
        self.assertFalse(result.accepted)
        self.assertEqual(len(result.trace_id), 32)
        self.assertIsNone(result.port_result)


if __name__ == "__main__":
    unittest.main()
