import asyncio
import unittest

from safe_output import (
    OutputRequest,
    SafeOutputCoordinator,
    SafetySupervisor,
    SafetyViolation,
    snapshot_from_live,
)


def live_state(**overrides):
    base = {
        "battery_voltage": 12.4,
        "current": 0.0,
        "temp_ext": 25.0,
        "temp_int": 32.0,
        "input_voltage": 64.0,
        "switch": "off",
        "ovp_triggered": "off",
        "ocp_triggered": "off",
        "set_voltage": 16.3,
        "set_current": 2.0,
        "ovp": 16.4,
        "ocp": 2.1,
    }
    base.update(overrides)
    return base


class FakeAdapter:
    def __init__(self):
        self.live = live_state()
        self.calls = []
        self.fail_method = None
        self.readback_override = {}

    async def get_all_live(self):
        self.calls.append("get_all_live")
        data = dict(self.live)
        data.update(self.readback_override)
        return data

    async def _set(self, name, key, value):
        self.calls.append(name)
        if self.fail_method == name:
            return False
        self.live[key] = value
        return True

    async def set_ovp(self, value):
        return await self._set("set_ovp", "ovp", value)

    async def set_ocp(self, value):
        return await self._set("set_ocp", "ocp", value)

    async def set_voltage(self, value):
        return await self._set("set_voltage", "set_voltage", value)

    async def set_current(self, value):
        return await self._set("set_current", "set_current", value)

    async def turn_on(self, entity_id=None):
        self.calls.append("turn_on")
        if self.fail_method == "turn_on":
            return False
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.calls.append("turn_off")
        if self.fail_method == "turn_off":
            return False
        self.live["switch"] = "off"
        return True


class SafetySupervisorTests(unittest.TestCase):
    def test_expert_17_5v_is_allowed_when_recipe_explicitly_allows_it(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state())
        assert telemetry is not None
        decision = supervisor.preflight(
            OutputRequest(17.5, 3.0, 17.6, 3.1, recipe_voltage_ceiling_v=17.5),
            telemetry,
        )
        self.assertTrue(decision.allowed)

    def test_recipe_ceiling_is_not_same_as_global_absolute_ceiling(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state())
        assert telemetry is not None
        decision = supervisor.preflight(
            OutputRequest(16.4, 2.0, 16.5, 2.1, recipe_voltage_ceiling_v=16.3),
            telemetry,
        )
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.REQUEST_OVER_RECIPE_CEILING, decision.violations)

    def test_missing_external_temperature_fails_closed(self):
        self.assertIsNone(snapshot_from_live(live_state(temp_ext=None)))

    def test_missing_internal_temperature_fails_closed(self):
        self.assertIsNone(snapshot_from_live(live_state(temp_int="unavailable")))

    def test_hot_power_supply_blocks_enable(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(temp_int=55.0))
        assert telemetry is not None
        decision = supervisor.preflight(
            OutputRequest(16.3, 2.0, 16.4, 2.1, recipe_voltage_ceiling_v=16.3),
            telemetry,
        )
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.POWER_SUPPLY_TOO_HOT, decision.violations)


class SafeOutputCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.request = OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3)

    def test_happy_path_programs_protections_before_output(self):
        adapter = FakeAdapter()
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertTrue(result.enabled)
        self.assertEqual(
            adapter.calls,
            [
                "get_all_live",
                "set_ovp",
                "set_ocp",
                "set_voltage",
                "set_current",
                "get_all_live",
                "turn_on",
                "get_all_live",
            ],
        )

    def test_programming_failure_forces_output_off(self):
        adapter = FakeAdapter()
        adapter.fail_method = "set_current"
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.PROGRAMMING_FAILED, result.violations)
        self.assertIn("turn_off", adapter.calls)
        self.assertNotIn("turn_on", adapter.calls)

    def test_readback_mismatch_forces_output_off(self):
        adapter = FakeAdapter()
        adapter.readback_override = {"set_voltage": 14.0}
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.READBACK_MISMATCH, result.violations)
        self.assertIn("turn_off", adapter.calls)
        self.assertNotIn("turn_on", adapter.calls)

    def test_output_already_on_is_never_reprogrammed_in_enable_path(self):
        adapter = FakeAdapter()
        adapter.live["switch"] = "on"
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.OUTPUT_ALREADY_ON, result.violations)
        self.assertEqual(adapter.calls, ["get_all_live"])

    def test_post_enable_input_drop_forces_output_off(self):
        adapter = FakeAdapter()
        original_turn_on = adapter.turn_on

        async def turn_on_then_drop(entity_id=None):
            result = await original_turn_on(entity_id)
            adapter.live["input_voltage"] = 55.0
            return result

        adapter.turn_on = turn_on_then_drop
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))

        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.INPUT_VOLTAGE_LOW, result.violations)
        self.assertIn(SafetyViolation.POST_ENABLE_VERIFY_FAILED, result.violations)
        self.assertEqual(adapter.live["switch"], "off")

    def test_post_enable_setpoint_drift_forces_output_off(self):
        adapter = FakeAdapter()
        original_turn_on = adapter.turn_on

        async def turn_on_then_drift(entity_id=None):
            result = await original_turn_on(entity_id)
            adapter.live["set_voltage"] = 15.0
            return result

        adapter.turn_on = turn_on_then_drift
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))

        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.READBACK_MISMATCH, result.violations)
        self.assertEqual(adapter.live["switch"], "off")

    def test_failed_cleanup_reports_unconfirmed_off(self):
        adapter = FakeAdapter()
        adapter.fail_method = "set_current"

        async def cannot_confirm_off(entity_id=None):
            adapter.calls.append("turn_off")
            return False

        adapter.turn_off = cannot_confirm_off
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))

        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.PROGRAMMING_FAILED, result.violations)
        self.assertIn(SafetyViolation.OUTPUT_OFF_UNCONFIRMED, result.violations)
        self.assertIn("OFF was not confirmed", result.detail)


if __name__ == "__main__":
    unittest.main()
