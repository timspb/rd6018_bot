from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from application.runtime_start_service import RuntimeStartService
from application.start_execution_contract import (
    DryRunExecutionPort,
    StartExecutionRequest,
    request_from_trace,
)
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
    async def get_all_live(self):
        return live()


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


def make_request():
    result = asyncio.run(
        StartPreflightService(FakeApp()).evaluate(
            StartRequest(
                profile="AGM",
                capacity_ah=70,
                battery_identity=BatteryIdentity("contract-battery", BatteryChemistry.AGM, 70),
                operator="contract-test",
            )
        )
    )
    plan = approved_plan_from_preflight(result)
    return RuntimeStartService().create_execution_request(plan, trace_id="trace-001", execution_metadata={"source": "test"})


class StartExecutionContractTests(unittest.TestCase):
    def test_request_is_immutable_and_has_no_runtime_objects(self):
        request = make_request()
        self.assertIsInstance(request, StartExecutionRequest)
        self.assertEqual(request.trace_id, "trace-001")
        with self.assertRaises(AttributeError):
            request.trace_id = "changed"
        with self.assertRaises(TypeError):
            request.execution_metadata["source"] = "changed"
        self.assertNotIn("hass", request.__dict__)
        self.assertNotIn("controller", request.__dict__)
        self.assertNotIn("connector", request.__dict__)

    def test_dry_run_port_accepts_valid_request(self):
        result = DryRunExecutionPort().submit(make_request())
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "dry_run_request_accepted")
        self.assertFalse(result.physical_execution)

    def test_denied_trace_cannot_become_request(self):
        request = make_request()
        denied_trace = SimpleNamespace(
            allowed=False,
            ownership_decision="denied",
            session_decision="clear",
            safety_decision="accepted",
            telemetry_evidence={"output_on": False},
        )
        with self.assertRaises(ValueError):
            request_from_trace(request.plan, denied_trace, trace_id="trace-denied")


if __name__ == "__main__":
    unittest.main()
