"""Safe output transaction tests for the current V/I-only software contract."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from runtime.safety.output_policy import (
    OutputAdapter,
    OutputRequest,
    SafetySupervisor,
    SafetyViolation,
    snapshot_from_live,
)
from application.safe_output_coordinator import SafeOutputCoordinator


def live_state(**overrides):
    stamp = datetime.now(timezone.utc).isoformat()
    live = {
        "battery_voltage": 12.4,
        "voltage": 0.0,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 32.0,
        "switch": "off",
        "set_voltage": 16.3,
        "set_current": 2.0,
        "set_voltage_readback_v2": 16.3,
        "set_current_readback_v2": 2.0,
        "protection_code": 0,
        "_meta": {
            key: {"status": "ok", "last_reported": stamp, "last_updated": stamp}
            for key in (
                "battery_voltage", "voltage", "current", "temp_ext", "temp_int",
                "switch", "set_voltage_readback_v2", "set_current_readback_v2",
                "protection_code",
            )
        },
    }
    live.update(overrides)
    return live


class FakeAdapter:
    def __init__(self):
        self.live = live_state()
        self.calls = []
        self.fail_method = None
        self.readback_override = {}
        self.turn_on_exception = None

    async def get_all_live(self):
        self.calls.append("get_all_live")
        return {**self.live, **self.readback_override}

    async def set_voltage(self, value):
        self.calls.append("set_voltage")
        if self.fail_method == "set_voltage":
            return False
        self.live["set_voltage"] = value
        self.live["set_voltage_readback_v2"] = value
        return True

    async def set_current(self, value):
        self.calls.append("set_current")
        if self.fail_method == "set_current":
            return False
        self.live["set_current"] = value
        self.live["set_current_readback_v2"] = value
        return True

    async def turn_on(self, entity_id=None):
        self.calls.append("turn_on")
        if self.turn_on_exception:
            raise self.turn_on_exception
        if self.fail_method == "turn_on":
            return False
        self.live.update(switch="on", voltage=self.live["set_voltage"],
                         current=self.live["set_current"])
        return True

    async def turn_off(self, entity_id=None):
        self.calls.append("turn_off")
        if self.fail_method == "turn_off":
            return False
        self.live.update(switch="off", voltage=0.0, current=0.0)
        return True


class SafeOutputTests(unittest.TestCase):
    def test_output_adapter_contract_matches_supported_v_i_transaction(self):
        declared_methods = {
            name for name, value in vars(OutputAdapter).items()
            if callable(value) and not name.startswith("_")
        }
        self.assertEqual(
            declared_methods,
            {"get_all_live", "set_voltage", "set_current", "turn_on", "turn_off"},
        )
        adapter = FakeAdapter()
        self.assertFalse(hasattr(adapter, "set_ovp"))
        self.assertFalse(hasattr(adapter, "set_ocp"))
        result = asyncio.run(
            SafeOutputCoordinator(adapter).enable(OutputRequest(16.3, 2.0, 16.3))
        )
        self.assertTrue(result.enabled, result.detail)

    def test_legacy_three_argument_output_request_keeps_optional_protection_fields(self):
        request = OutputRequest(14.4, 2.0, 14.4)
        self.assertEqual(request.recipe_voltage_ceiling_v, 14.4)
        self.assertIsNone(request.ovp_v)
        self.assertIsNone(request.ocp_a)

    def test_r16_ovp_ocp_are_diagnostic_only_but_opp_blocks_preflight(self):
        supervisor = SafetySupervisor()
        for code, expected in ((1, "ovp"), (2, "ocp"), (3, "opp")):
            with self.subTest(code=code):
                telemetry = snapshot_from_live(live_state(protection_code=code))
                self.assertEqual(telemetry.protection_status.value, expected)
                decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.3), telemetry)
                if code == 3:
                    self.assertFalse(decision.allowed)
                    self.assertIn(SafetyViolation.PROTECTION_ALREADY_TRIPPED, decision.violations)
                else:
                    self.assertTrue(decision.allowed, decision.detail)

    def test_temperature_and_battery_envelopes_still_block_start(self):
        supervisor = SafetySupervisor()
        for live, expected in (
            (live_state(temp_int=55.0), SafetyViolation.POWER_SUPPLY_TOO_HOT),
            (live_state(temp_ext=45.0), SafetyViolation.BATTERY_TOO_HOT),
            (live_state(battery_voltage=21.0), SafetyViolation.BATTERY_NOT_PLAUSIBLE),
        ):
            telemetry = snapshot_from_live(live)
            decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.3), telemetry)
            self.assertIn(expected, decision.violations)

    def test_missing_or_stale_critical_telemetry_fails_closed(self):
        supervisor = SafetySupervisor()
        self.assertIsNone(snapshot_from_live(live_state(temp_int=None)))
        old = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
        stale = live_state()
        stale["_meta"]["current"] = {"status": "ok", "last_updated": old}
        self.assertIsNone(snapshot_from_live(stale))
        telemetry = snapshot_from_live(live_state())
        self.assertTrue(supervisor.preflight(OutputRequest(16.3, 2.0, 16.3), telemetry).allowed)

    def test_v_i_readback_mismatch_fails_closed(self):
        adapter = FakeAdapter()
        adapter.readback_override = {"set_voltage_readback_v2": 14.0}
        result = asyncio.run(SafeOutputCoordinator(adapter, readback_timeout_s=0.0).enable(
            OutputRequest(16.3, 2.0, 16.3)))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.READBACK_MISMATCH, result.violations)
        self.assertNotIn("turn_on", adapter.calls)

    def test_enable_programs_only_v_i_then_verifies_before_output(self):
        adapter = FakeAdapter()
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(OutputRequest(16.3, 2.0, 16.3)))
        self.assertTrue(result.enabled, result.detail)
        self.assertEqual(adapter.calls, [
            "get_all_live", "set_voltage", "set_current", "get_all_live",
            "turn_on", "get_all_live",
        ])

    def test_programming_failure_forces_output_off_without_enable(self):
        adapter = FakeAdapter()
        adapter.fail_method = "set_current"
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(OutputRequest(16.3, 2.0, 16.3)))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.PROGRAMMING_FAILED, result.violations)
        self.assertIn("turn_off", adapter.calls)
        self.assertNotIn("turn_on", adapter.calls)

    def test_measured_voltage_and_current_caps_force_output_off(self):
        for key, measured, request, expected in (
            ("voltage", 16.7, OutputRequest(16.3, 2.0, 16.3), SafetyViolation.MEASURED_OUTPUT_OVER_LIMIT),
            ("current", 12.2, OutputRequest(17.0, 12.0, 17.5), SafetyViolation.CURRENT_OVER_ABSOLUTE_LIMIT),
        ):
            adapter = FakeAdapter()
            original = adapter.turn_on

            async def turn_on_then_exceed(entity_id=None, *, _key=key, _value=measured):
                result = await original(entity_id)
                adapter.live[_key] = _value
                return result

            adapter.turn_on = turn_on_then_exceed
            result = asyncio.run(SafeOutputCoordinator(adapter).enable(request))
            self.assertFalse(result.enabled)
            self.assertIn(expected, result.violations)
            self.assertEqual(adapter.live["switch"], "off")

    def test_opp_after_enable_forces_output_off(self):
        adapter = FakeAdapter()
        original = adapter.turn_on

        async def turn_on_then_trip(entity_id=None):
            result = await original(entity_id)
            adapter.live["protection_code"] = 3
            return result

        adapter.turn_on = turn_on_then_trip
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(OutputRequest(16.3, 2.0, 16.3)))
        self.assertFalse(result.enabled)
        self.assertEqual(adapter.live["switch"], "off")


if __name__ == "__main__":
    unittest.main()
