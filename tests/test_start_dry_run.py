from __future__ import annotations

import unittest
from types import SimpleNamespace

from application.start_dry_run import StartDryRunIntegrationGate
from application.start_execution_adapter import StartExecutionAdapter
from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
from pb_domain import BatteryChemistry, BatteryIdentity


def live(**overrides):
    value = {
        "battery_voltage": 13.5,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 30.0,
        "input_voltage": 60.0,
        "switch": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "_freshness": {
            key: 0.0
            for key in ("battery_voltage", "current", "temp_ext", "temp_int", "switch", "ovp_triggered", "ocp_triggered")
        },
    }
    value.update(overrides)
    return value


class FakeHass:
    def __init__(self, value):
        self.value = value
        self.writes = []

    async def get_all_live(self):
        return dict(self.value)


class FakeController:
    is_active = False
    start_calls = 0

    def _main_target(self, _temperature):
        return 14.4, 7.0

    def _prep_target(self, _temperature):
        return 12.0, 0.7

    def start(self, *_args, **_kwargs):
        self.start_calls += 1
        raise AssertionError("START mutation must not be called")


class FakeApp:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1

    def __init__(self, value=None):
        self.hass = FakeHass(value or live())
        self.charge_controller = FakeController()
        self.rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


async def build_plan(app):
    request = StartRequest(
        profile="AGM",
        capacity_ah=70,
        battery_identity=BatteryIdentity("dry-run-battery", BatteryChemistry.AGM, 70),
        operator="dry-run-test",
    )
    result = await StartPreflightService(app).evaluate(request)
    return approved_plan_from_preflight(result)


class StartDryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_dry_run_reads_real_composition_without_mutation(self):
        app = FakeApp()
        plan = await build_plan(app)
        report = await StartExecutionAdapter().dry_run_integration(plan, app)
        self.assertTrue(report.allowed)
        self.assertEqual(report.ownership_decision, "available")
        self.assertEqual(report.session_decision, "clear")
        self.assertEqual(report.controller_handoff_decision, "deferred_read_only")
        self.assertIn("future_failure_requires_verified_off", report.rollback_plan)
        self.assertEqual(app.charge_controller.start_calls, 0)
        self.assertEqual(app.hass.writes, [])

    async def test_denied_dry_run_reports_ownership_and_session(self):
        app = FakeApp()
        app.rd_control_mode_manager.hands_off = True
        app.charge_controller.is_active = True
        plan = await build_plan(FakeApp())
        report = await StartDryRunIntegrationGate().evaluate(plan, app)
        self.assertFalse(report.allowed)
        self.assertIn("ownership_not_available", report.reasons)
        self.assertIn("active_charge_session", report.reasons)

    async def test_failed_handoff_probe_is_reported_without_execution(self):
        app = FakeApp()
        plan = await build_plan(app)
        report = await StartDryRunIntegrationGate().evaluate(plan, app, handoff_probe=lambda _plan: False)
        self.assertFalse(report.allowed)
        self.assertEqual(report.controller_handoff_decision, "probe_denied")
        self.assertIn("controller_handoff_probe_failed", report.reasons)
        self.assertEqual(app.charge_controller.start_calls, 0)

    async def test_output_on_fails_closed_and_preserves_rollback_contract(self):
        app = FakeApp(live(switch="on"))
        plan = await build_plan(FakeApp())
        report = await StartDryRunIntegrationGate().evaluate(plan, app)
        self.assertFalse(report.allowed)
        self.assertIn("output_already_on", report.reasons)
        self.assertEqual(report.physical_execution_blocked_reason, "dry_run_physical_execution_disabled")


if __name__ == "__main__":
    unittest.main()
