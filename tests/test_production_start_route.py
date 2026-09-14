import asyncio
import unittest
from types import SimpleNamespace
from pathlib import Path

import bot
from application.intents import OperatorIntent, OperatorIntentKind
from application.production_start_route import ProductionStartRouteAdapter
from application.production_start_execution_port import ProductionStartMode
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
    def test_production_composition_installs_one_dry_run_route(self):
        self.assertIsInstance(bot._v3_production_start_route, ProductionStartRouteAdapter)
        self.assertEqual(bot._v3_production_start_route.mode, ProductionStartMode.DRY_RUN)

        source = Path("v2_bootstrap.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('F.data == "v2_battery_start"'), 1)
        self.assertNotIn("start_profile_transactional(app, call, pending)", source)

    def test_default_route_is_dry_run_and_preserves_trace(self):
        adapter = ProductionStartRouteAdapter(_App())
        result = asyncio.run(adapter.submit(_intent()))
        self.assertTrue(result.accepted)
        self.assertEqual(adapter.mode, ProductionStartMode.DRY_RUN)
        self.assertEqual(result.port_result.reason, "dry_run_routed_no_mutation")
        self.assertEqual(result.port_result.request.trace_id, result.trace_id)

    def test_active_route_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ProductionStartRouteAdapter(_App(), mode=ProductionStartMode.ACTIVE)

    def test_denied_preflight_does_not_create_plan(self):
        app = _App()
        app.rd_control_mode_manager.hands_off = True
        result = asyncio.run(ProductionStartRouteAdapter(app).submit(_intent()))
        self.assertFalse(result.accepted)
        self.assertIsNone(result.plan)
        self.assertIn("preflight_denied:hands_off", result.reason)


if __name__ == "__main__":
    unittest.main()
