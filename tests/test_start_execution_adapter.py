from __future__ import annotations

import unittest
from types import SimpleNamespace

from application.start_execution_adapter import StartExecutionAdapter, StartExecutionMode
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

    def _main_target(self, _temperature):
        return 14.4, 7.0

    def _prep_target(self, _temperature):
        return 12.0, 0.7


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


def approved_plan():
    app = FakeApp()
    request = StartRequest(
        profile="AGM",
        capacity_ah=70,
        battery_identity=BatteryIdentity("adapter-battery", BatteryChemistry.AGM, 70),
        operator="adapter-test",
    )
    import asyncio

    result = asyncio.run(StartPreflightService(app).evaluate(request))
    return approved_plan_from_preflight(result), app


class StartExecutionAdapterTests(unittest.TestCase):
    def test_shadow_creates_trace_without_controller_or_physical_mutation(self):
        plan, app = approved_plan()
        result = StartExecutionAdapter().execute(plan, StartExecutionMode.SHADOW)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "shadow_trace_created")
        self.assertFalse(result.handoff_plan.physical_execution)
        self.assertEqual(app.hass.writes, [])
        self.assertFalse(app.charge_controller.is_active)

    def test_dry_run_creates_handoff_plan_without_execution(self):
        plan, app = approved_plan()
        result = StartExecutionAdapter().execute(plan, StartExecutionMode.DRY_RUN)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "dry_run_handoff_created")
        self.assertEqual(result.handoff_plan.controller_handoff, "deferred_no_mutation")
        self.assertEqual(app.hass.writes, [])

    def test_denied_plan_is_rejected(self):
        plan, _ = approved_plan()
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
        result = StartExecutionAdapter().execute(denied, StartExecutionMode.DRY_RUN)
        self.assertFalse(result.accepted)
        self.assertIn("ownership_not_available", result.reason)

    def test_active_is_feature_gated_off_by_default(self):
        plan, _ = approved_plan()
        result = StartExecutionAdapter().execute(plan, StartExecutionMode.ACTIVE)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "active_execution_disabled")


if __name__ == "__main__":
    unittest.main()
