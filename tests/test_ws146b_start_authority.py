import asyncio
import ast
import pathlib
import unittest
from types import SimpleNamespace

from application.intents import OperatorIntent, OperatorIntentKind
from application.production_start_execution_port import ProductionStartExecutionPort, ProductionStartMode
from application.start_authority import StartAuthority
from application.start_orchestration import StartOrchestration
from application.start_request import StartRequest
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, ChargeIntent


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
            "intent": ChargeIntent.NORMAL,
            "condition": BatteryCondition.UNKNOWN,
        },
    )


class WS146BStartAuthorityTests(unittest.TestCase):
    def setUp(self):
        _App.rd_control_mode_manager.hands_off = False
        _App.charge_controller.is_active = False

    def test_authority_owns_admission_and_creates_session_only_after_approval(self):
        decision = asyncio.run(StartAuthority(_App()).authorize(_intent()))
        self.assertTrue(decision.accepted)
        self.assertIsNotNone(decision.plan)
        self.assertTrue(decision.identity.trace_id)
        self.assertTrue(decision.identity.session_id)

    def test_denied_preflight_is_fail_closed_without_session_identity(self):
        app = _App()
        app.rd_control_mode_manager.hands_off = True
        decision = asyncio.run(StartAuthority(app).authorize(_intent()))
        self.assertFalse(decision.accepted)
        self.assertIsNone(decision.plan)
        self.assertIsNone(decision.identity.session_id)
        self.assertIn("preflight_denied:hands_off", decision.reason)

    def test_orchestration_orders_audit_before_handoff_and_propagates_identity(self):
        orchestration = StartOrchestration(
            StartAuthority(_App()),
            ProductionStartExecutionPort(),
            mode=ProductionStartMode.DRY_RUN,
        )
        result = asyncio.run(orchestration.submit(_intent()))
        self.assertTrue(result.accepted)
        self.assertEqual(
            [event.event_type for event in result.audit],
            ["START_AUTHORIZED", "START_HANDOFF_PREPARED", "START_HANDOFF_ACCEPTED"],
        )
        self.assertLess(result.audit[0].timestamp, result.audit[1].timestamp)
        self.assertIsNotNone(result.port_result.request)
        request = result.port_result.request
        self.assertEqual(request.trace_id, result.identity.trace_id)
        self.assertEqual(request.execution_metadata["correlation_metadata"]["session_id"], result.identity.session_id)

    def test_dry_run_and_active_share_authority_but_active_remains_gated(self):
        authority = StartAuthority(_App())
        dry = StartOrchestration(authority, ProductionStartExecutionPort(), mode=ProductionStartMode.DRY_RUN)
        active = StartOrchestration(authority, ProductionStartExecutionPort(), mode=ProductionStartMode.ACTIVE)
        dry_result = asyncio.run(dry.submit(_intent()))
        active_result = asyncio.run(active.submit(_intent()))
        self.assertTrue(dry_result.authority.accepted)
        self.assertTrue(active_result.authority.accepted)
        self.assertTrue(dry_result.accepted)
        self.assertFalse(active_result.accepted)
        self.assertEqual(active_result.reason, "active_execution_disabled")

    def test_route_is_transport_adapter_not_second_authority(self):
        source = (pathlib.Path(__file__).parents[1] / "application" / "production_start_route.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        self.assertEqual(names, {"ProductionStartRouteResult", "ProductionStartRouteAdapter"})
        self.assertNotIn("StartPreflightService", source)
        self.assertIn("StartAuthority", source)
        self.assertIn("StartOrchestration", source)


if __name__ == "__main__":
    unittest.main()
