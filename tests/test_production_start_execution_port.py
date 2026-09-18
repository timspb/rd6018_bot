from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from pathlib import Path

from application.production_start_execution_port import ProductionStartExecutionPort, ProductionStartMode
from application.production_start_runner import ProductionStartRunner
from application.start_execution_contract import StartExecutionRequest
from application.start_activation_policy import StartActivationPolicy, StartExecutionMode
from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
from application.v2_start_transaction_adapter import (
    StartExecutionStatus,
    V2StartTransactionAdapter,
    V2TransactionOutcome,
)
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
        result = ProductionStartExecutionPort().submit(
            make_plan(), trace_id="trace-shadow", session_id="session-shadow", mode=ProductionStartMode.SHADOW
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.trace_id, "trace-shadow")
        self.assertEqual(result.request.trace_id, "trace-shadow")
        self.assertEqual(result.request.session_id, "session-shadow")

    def test_dry_run_routes_through_v2_adapter_without_runner(self):
        result = ProductionStartExecutionPort().submit(make_plan(), trace_id="trace-dry", mode=ProductionStartMode.DRY_RUN)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "dry_run_routed_no_mutation")
        self.assertEqual(result.request.trace_id, "trace-dry")

    def test_active_gate_rejects(self):
        result = ProductionStartExecutionPort().submit(make_plan(), trace_id="trace-active", mode=ProductionStartMode.ACTIVE)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "active_execution_disabled")

    def test_sync_active_path_is_fail_closed_and_does_not_call_async_owner(self):
        calls = []

        class Runner:
            def execute(self, _request):
                calls.append("sync")
                return V2TransactionOutcome(started=True, reason="unexpected")

            async def execute_async(self, _request):
                calls.append("async")
                return V2TransactionOutcome(started=True, reason="unexpected")

        result = ProductionStartExecutionPort(
            activation_policy=StartActivationPolicy(
                execution_mode=StartExecutionMode.ACTIVE,
                explicit_active_enable=True,
                bench_validation_passed=True,
                rollback_validation_passed=True,
                physical_gate_passed=True,
            ),
            production_runner=Runner(),
        ).submit(make_plan(), trace_id="trace-sync-active", mode=ProductionStartMode.ACTIVE)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "active_requires_async_handoff")
        self.assertEqual(calls, [])

    def test_async_active_path_awaits_owner_and_propagates_result(self):
        calls = []
        plan = make_plan()

        async def async_owner(request):
            calls.append(request)
            return V2TransactionOutcome(
                trace_id=request.trace_id,
                started=True,
                reason="started",
            )

        async def run():
            return await ProductionStartExecutionPort(
                activation_policy=StartActivationPolicy(
                    execution_mode=StartExecutionMode.ACTIVE,
                    explicit_active_enable=True,
                    bench_validation_passed=True,
                    rollback_validation_passed=True,
                    physical_gate_passed=True,
                ),
                production_runner=ProductionStartRunner(
                    V2StartTransactionAdapter(),
                    StartActivationPolicy(
                        execution_mode=StartExecutionMode.ACTIVE,
                        explicit_active_enable=True,
                        bench_validation_passed=True,
                        rollback_validation_passed=True,
                        physical_gate_passed=True,
                    ),
                    async_owner,
                ),
            ).submit_active(plan, trace_id="trace-async-active")

        result = asyncio.run(run())
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "started")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].trace_id, "trace-async-active")

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
