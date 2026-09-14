from __future__ import annotations

import unittest
from types import SimpleNamespace

from application.start_preflight import StartPreflightService, compare_start_preflight
from application.start_request import StartRequest
from application.start_plan import (
    ApprovedStartPlan,
    approved_plan_from_preflight,
    compare_approved_start_plan,
)
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


class _Hass:
    def __init__(self, value):
        self.value = value
        self.writes = []

    async def get_all_live(self):
        return dict(self.value)

    async def turn_on(self, *args, **kwargs):
        self.writes.append(("turn_on", args, kwargs))


class _Controller:
    is_active = False
    battery_type = "AGM"

    def _prep_target(self, temperature):
        return 12.0, 0.7

    def _main_target(self, temperature):
        return 14.4, 7.0


class _App:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1

    def __init__(self, value=None):
        self.hass = _Hass(value or live())
        self.charge_controller = _Controller()
        self.rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


def request(profile="AGM"):
    return StartRequest(
        profile=profile,
        capacity_ah=70,
        battery_identity=BatteryIdentity("bat-1", BatteryChemistry.AGM, 70),
        operator="operator-1",
    )


class StartPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_agm_preview_is_allowed_without_writes(self):
        app = _App()
        result = await StartPreflightService(app).evaluate(request())
        self.assertTrue(result.allowed)
        self.assertEqual(result.chemistry, "agm")
        self.assertEqual(result.recipe_preview.recipe_id, "agm:normal")
        self.assertEqual(result.target_preview.stage, "MAIN")
        self.assertEqual(app.hass.writes, [])

    async def test_invalid_telemetry_is_denied(self):
        result = await StartPreflightService(_App(live(temp_ext="unavailable"))).evaluate(request())
        self.assertFalse(result.allowed)
        self.assertIn("invalid_or_stale_telemetry", result.reasons)

    async def test_hands_off_is_denied(self):
        app = _App()
        app.rd_control_mode_manager.hands_off = True
        result = await StartPreflightService(app).evaluate(request())
        self.assertFalse(result.allowed)
        self.assertIn("hands_off", result.reasons)

    async def test_active_session_is_denied(self):
        app = _App()
        app.charge_controller.is_active = True
        result = await StartPreflightService(app).evaluate(request())
        self.assertFalse(result.allowed)
        self.assertIn("active_charge_session", result.reasons)

    async def test_invalid_profile_is_denied(self):
        result = await StartPreflightService(_App()).evaluate(request("LiFePO4"))
        self.assertFalse(result.allowed)
        self.assertIn("invalid_profile", result.reasons)

    async def test_safety_deny_is_reported(self):
        result = await StartPreflightService(_App(live(ovp_triggered="on"))).evaluate(request())
        self.assertFalse(result.allowed)
        self.assertEqual(result.safety_status, "denied")

    async def test_shadow_comparison_reports_target_mismatch(self):
        result = await StartPreflightService(_App()).evaluate(request())
        comparison = compare_start_preflight(
            {
                "profile": "AGM",
                "chemistry": "agm",
                "allowed": True,
                "ownership_status": "available",
                "telemetry_status": "valid",
                "safety_status": "allowed",
                "recipe_id": "agm:normal",
                "target_voltage_v": 14.0,
                "target_current_a": 7.0,
            },
            result,
        )
        self.assertEqual(comparison.status, "MISMATCH")
        self.assertIn("target_voltage_v", comparison.fields)

    async def test_approved_agm_plan_contains_only_preview_data(self):
        result = await StartPreflightService(_App()).evaluate(request())
        plan = approved_plan_from_preflight(result)
        self.assertIsInstance(plan, ApprovedStartPlan)
        self.assertEqual(plan.profile, "AGM")
        self.assertEqual(plan.recipe_id, "agm:normal")
        self.assertEqual(plan.target_preview.stage, "MAIN")
        self.assertEqual(plan.current_limit_preview_a, 7.0)
        self.assertEqual(plan.battery_identity.chemistry, BatteryChemistry.AGM)
        self.assertNotIn("hass", plan.__dict__)
        self.assertNotIn("controller", plan.__dict__)

    async def test_denied_preflight_cannot_create_plan(self):
        result = await StartPreflightService(_App(live(ovp_triggered="on"))).evaluate(request())
        with self.assertRaises(ValueError):
            approved_plan_from_preflight(result)

    async def test_plan_is_immutable_and_evidence_is_read_only(self):
        result = await StartPreflightService(_App()).evaluate(request())
        plan = approved_plan_from_preflight(result)
        with self.assertRaises((AttributeError, TypeError)):
            plan.profile = "EFB"
        with self.assertRaises(TypeError):
            plan.telemetry_evidence["output_on"] = True

    async def test_plan_comparator_reports_v2_mismatch(self):
        result = await StartPreflightService(_App()).evaluate(request())
        plan = approved_plan_from_preflight(result)
        comparison = compare_approved_start_plan(
            {
                "profile": "AGM",
                "chemistry": "agm",
                "recipe_id": "agm:normal",
                "target_voltage_v": 14.4,
                "target_current_a": 7.0,
                "current_limit_preview_a": 7.0,
                "ownership_status": "available",
                "safety_status": "allowed",
            },
            plan,
        )
        self.assertEqual(comparison.status, "MATCH")


if __name__ == "__main__":
    unittest.main()
