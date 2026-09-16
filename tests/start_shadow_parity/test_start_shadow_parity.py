from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from application.runtime_start_service import RuntimeStartService, compare_start_execution_trace
from application.start_plan import approved_plan_from_preflight
from application.start_preflight import StartPreflightService
from application.start_request import StartRequest
from pb_domain import BatteryChemistry, BatteryIdentity


GOLDEN = json.loads((Path(__file__).with_name("golden_traces.json")).read_text(encoding="utf-8"))


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

    def __init__(self, target=(14.4, 7.0)):
        self.target = target

    def _prep_target(self, _temperature):
        return 12.0, 0.7

    def _main_target(self, _temperature):
        return self.target


class FakeApp:
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1

    def __init__(self, value=None, *, target=(14.4, 7.0)):
        self.hass = FakeHass(value or live())
        self.charge_controller = FakeController(target)
        self.rd_control_mode_manager = SimpleNamespace(hands_off=False)

    @staticmethod
    def _cap_current(value):
        return min(float(value), 12.0)


def request(profile):
    chemistry = {
        "AGM": BatteryChemistry.AGM,
        "EFB": BatteryChemistry.EFB,
        "Ca/Ca": BatteryChemistry.CA_CA,
        "Custom": BatteryChemistry.CUSTOM,
    }.get(profile)
    identity = BatteryIdentity(f"{profile}-battery", chemistry, 70)
    return StartRequest(profile=profile, capacity_ah=70, battery_identity=identity, operator="parity-test")


class StartShadowParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_matrix_matches_golden_v2_values(self):
        for profile, expected in GOLDEN["success"].items():
            with self.subTest(profile=profile):
                result = await StartPreflightService(FakeApp()).evaluate(request(profile))
                self.assertTrue(result.allowed, result.reasons)
                trace = RuntimeStartService().require_approved_trace(approved_plan_from_preflight(result))
                comparison = compare_start_execution_trace(
                    {
                        "profile": profile,
                        **expected,
                        "ownership": "accepted",
                        "session": "clear",
                        "safety": "accepted",
                        "allowed": True,
                    },
                    trace,
                )
                self.assertEqual(comparison.status, "MATCH", comparison.fields)

    async def test_deny_matrix_matches_golden_reasons(self):
        cases = {
            "HANDS_OFF": (FakeApp(), request("AGM"), lambda app: setattr(app.rd_control_mode_manager, "hands_off", True)),
            "active_session": (FakeApp(), request("AGM"), lambda app: setattr(app.charge_controller, "is_active", True)),
            "stale_telemetry": (FakeApp(live(temp_ext="unavailable")), request("AGM"), lambda app: None),
            "invalid_profile": (FakeApp(), StartRequest(profile="LiFePO4", capacity_ah=70, operator="parity-test"), lambda app: None),
            "unsafe_voltage": (FakeApp(target=(20.0, 7.0)), request("AGM"), lambda app: None),
            "unsafe_temperature": (FakeApp(live(temp_ext=80.0)), request("AGM"), lambda app: None),
            "output_already_enabled": (FakeApp(live(switch="on")), request("AGM"), lambda app: None),
        }
        for case, (app, start_request, setup) in cases.items():
            with self.subTest(case=case):
                setup(app)
                result = await StartPreflightService(app).evaluate(start_request)
                self.assertFalse(result.allowed)
                for reason in GOLDEN["deny"][case]:
                    self.assertIn(reason, result.reasons, (case, result.reasons))

    async def test_shadow_matrix_has_no_write_or_controller_mutation(self):
        app = FakeApp()
        result = await StartPreflightService(app).evaluate(request("AGM"))
        plan = approved_plan_from_preflight(result)
        RuntimeStartService().require_approved_trace(plan)
        self.assertEqual(app.hass.writes, [])
        self.assertFalse(app.charge_controller.is_active)


if __name__ == "__main__":
    unittest.main()
