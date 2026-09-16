from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from pathlib import Path

from application.production_start_execution_port import ProductionStartExecutionPort, ProductionStartMode
from application.start_execution_contract import StartExecutionRequest
from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
from application.v2_start_transaction_adapter import StartExecutionStatus, V2TransactionOutcome
from pb_domain import BatteryChemistry, BatteryIdentity


class FakeHass:
    async def get_all_live(self):
        return {
            "battery_voltage": 13.5, "current": 0.0, "temp_ext": 25.0, "temp_int": 30.0,
            "input_voltage": 60.0, "switch": "off", "ovp_triggered": "off", "ocp_triggered": "off",
            "_freshness": {key: 0.0 for key in ("battery_voltage", "current", "temp_ext", "temp_int", "switch", "ovp_triggered", "ocp_triggered")},
        }


class FakeController:
    is_active = False
    start_calls = 0

    def _main_target(self, _temperature):
        return 14.4, 7.0

    def _prep_target(self, _temperature):
        return 12.0, 0.7


class FakeApp:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    hass = FakeHass()
    charge_controller = FakeController()
    rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


def make_plan():
    result = asyncio.run(
        StartPreflightService(FakeApp()).evaluate(
            StartRequest(
                profile="AGM", capacity_ah=70,
                battery_identity=BatteryIdentity("port-battery", BatteryChemistry.AGM, 70),
                operator="port-test",
            )
        )
    )
    return approved_plan_from_preflight(result)


class ProductionStartPortTests(unittest.TestCase):
    def test_shadow_path_propagates_trace_id(self):
        result = ProductionStartExecutionPort().submit(make_plan(), trace_id="trace-shadow", mode=ProductionStartMode.SHADOW)
        self.assertTrue(result.accepted)
        self.assertEqual(result.trace_id, "trace-shadow")
        self.assertEqual(result.request.trace_id, "trace-shadow")

    def test_dry_run_routes_through_v2_adapter_without_runner(self):
        result = ProductionStartExecutionPort().submit(make_plan(), trace_id="trace-dry", mode=ProductionStartMode.DRY_RUN)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "dry_run_routed_no_mutation")
        self.assertEqual(result.request.trace_id, "trace-dry")

    def test_active_gate_rejects(self):
        result = ProductionStartExecutionPort().submit(make_plan(), trace_id="trace-active", mode=ProductionStartMode.ACTIVE)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "active_execution_disabled")

    def test_v2_outcome_mapping_preserves_trace_id(self):
        port = ProductionStartExecutionPort()
        routed = port.submit(make_plan(), trace_id="trace-result", mode=ProductionStartMode.DRY_RUN)
        normalized = port.normalize_v2_outcome(
            routed.request,
            V2TransactionOutcome(started=False, session_cleared=True, output_off_confirmed=True, reason="failed_start"),
        )
        self.assertEqual(normalized.trace_id, "trace-result")
        self.assertEqual(normalized.status, StartExecutionStatus.FAILED)

    def test_no_duplicate_telegram_start_route_in_v2_bootstrap(self):
        source = Path("v2_bootstrap.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('F.data == "v2_battery_start"'), 1)


if __name__ == "__main__":
    unittest.main()
