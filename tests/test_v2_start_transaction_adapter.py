from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
from application.v2_start_transaction_adapter import (
    RollbackState,
    StartExecutionStatus,
    V2StartTransactionAdapter,
    V2TransactionOutcome,
)
from pb_domain import BatteryChemistry, BatteryIdentity


class FakeHass:
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
            "_freshness": {key: 0.0 for key in ("battery_voltage", "current", "temp_ext", "temp_int", "switch", "ovp_triggered", "ocp_triggered")},
        }


class FakeController:
    is_active = False

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
                profile="AGM",
                capacity_ah=70,
                battery_identity=BatteryIdentity("adapter-battery", BatteryChemistry.AGM, 70),
                operator="adapter-test",
            )
        )
    )
    return approved_plan_from_preflight(result)


class V2StartTransactionAdapterTests(unittest.TestCase):
    def test_prepare_maps_approved_plan_without_runtime_objects(self):
        transaction = V2StartTransactionAdapter().prepare(make_plan())
        self.assertEqual(transaction.profile, "AGM")
        self.assertEqual(transaction.chemistry, "agm")
        self.assertEqual(transaction.recipe_id, "agm:normal")
        self.assertEqual(transaction.target_voltage_v, 14.4)
        self.assertNotIn("controller", transaction.__dict__)
        self.assertNotIn("hass", transaction.__dict__)

    def test_denied_plan_cannot_be_prepared(self):
        plan = make_plan()
        denied = plan.__class__(
            profile=plan.profile,
            chemistry=plan.chemistry,
            recipe_id=plan.recipe_id,
            target_preview=plan.target_preview,
            current_limit_preview_a=plan.current_limit_preview_a,
            battery_identity=plan.battery_identity,
            ownership_result="hands_off",
            safety_result=plan.safety_result,
            telemetry_evidence=plan.telemetry_evidence,
        )
        with self.assertRaises(ValueError):
            V2StartTransactionAdapter().prepare(denied)

    def test_failed_start_normalizes_verified_off_and_cleared_session(self):
        result = V2StartTransactionAdapter().normalize(
            make_plan(),
            V2TransactionOutcome(
                output_off_confirmed=True,
                session_cleared=True,
                reason="safe_enable_failed",
            ),
        )
        self.assertEqual(result.status, StartExecutionStatus.FAILED)
        self.assertEqual(result.rollback, RollbackState.SESSION_CLEARED)

    def test_unconfirmed_failure_normalizes_containment(self):
        result = V2StartTransactionAdapter().normalize(
            make_plan(),
            V2TransactionOutcome(
                contained=True,
                output_off_unconfirmed=True,
                session_contained=True,
                reason="output_off_unconfirmed",
            ),
        )
        self.assertEqual(result.status, StartExecutionStatus.CONTAINED)
        self.assertEqual(result.rollback, RollbackState.SESSION_CONTAINED)

    def test_active_execution_is_disabled_and_runner_is_not_called(self):
        calls = []
        result = V2StartTransactionAdapter().execute(
            make_plan(),
            lambda _input: calls.append("called"),
        )
        self.assertEqual(result.status, StartExecutionStatus.DENIED)
        self.assertEqual(result.reason, "active_execution_disabled")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
