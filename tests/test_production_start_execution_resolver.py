from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from application.production_start_execution_resolver import ProductionStartExecutionResolver
from application.production_start_execution_port import ProductionStartMode, ProductionStartPortResult
from application.start_activation_policy import StartActivationPolicy, StartExecutionMode
from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
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


class _App:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    hass = _Hass()
    class _Controller:
        is_active = False

        def _main_target(self, _temperature):
            return 14.4, 7.0

        def _prep_target(self, _temperature):
            return 12.0, 0.7

    charge_controller = _Controller()
    rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


def make_plan():
    result = asyncio.run(StartPreflightService(_App()).evaluate(StartRequest(
        profile="AGM",
        capacity_ah=70,
        battery_identity=BatteryIdentity("resolver-battery", BatteryChemistry.AGM, 70),
        operator="resolver-test",
    )))
    return approved_plan_from_preflight(result)


def active_policy() -> StartActivationPolicy:
    return StartActivationPolicy(
        execution_mode=StartExecutionMode.ACTIVE,
        explicit_active_enable=True,
        bench_validation_passed=True,
        rollback_validation_passed=True,
        physical_gate_passed=True,
    )


class FakePort:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit(self, plan, *, trace_id, mode, execution_metadata=None, session_id=None):
        self.calls.append(f"submit:{mode.value}")
        return ProductionStartPortResult(True, mode, trace_id, "dry_run")

    async def submit_active(self, plan, *, trace_id, execution_metadata=None, session_id=None):
        self.calls.append("submit_active")
        return ProductionStartPortResult(True, ProductionStartMode.ACTIVE, trace_id, "started")


class ProductionStartExecutionResolverTests(unittest.TestCase):
    def test_no_authority_keeps_dry_run(self):
        port = FakePort()
        provider = SimpleNamespace(current_policy=lambda: StartActivationPolicy())
        result = asyncio.run(
            ProductionStartExecutionResolver(port, provider).resolve(make_plan(), trace_id="trace-deny")
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.mode, ProductionStartMode.DRY_RUN)
        self.assertEqual(port.calls, ["submit:dry_run"])

    def test_valid_authority_selects_active(self):
        port = FakePort()
        provider = SimpleNamespace(current_policy=active_policy)
        result = asyncio.run(
            ProductionStartExecutionResolver(port, provider).resolve(make_plan(), trace_id="trace-active")
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.mode, ProductionStartMode.ACTIVE)
        self.assertEqual(port.calls, ["submit_active"])

    def test_expired_authority_denies_active(self):
        port = FakePort()
        provider = SimpleNamespace(current_policy=lambda: StartActivationPolicy())
        result = asyncio.run(
            ProductionStartExecutionResolver(port, provider).resolve(make_plan(), trace_id="trace-expired")
        )
        self.assertEqual(result.mode, ProductionStartMode.DRY_RUN)
        self.assertNotIn("submit_active", port.calls)

    def test_revoked_authority_denies_active(self):
        port = FakePort()
        provider = SimpleNamespace(current_policy=lambda: StartActivationPolicy())
        result = asyncio.run(
            ProductionStartExecutionResolver(port, provider).resolve(make_plan(), trace_id="trace-revoked")
        )
        self.assertEqual(result.mode, ProductionStartMode.DRY_RUN)
        self.assertNotIn("submit_active", port.calls)


if __name__ == "__main__":
    unittest.main()
