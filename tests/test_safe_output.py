import asyncio
import unittest
from datetime import datetime, timedelta, timezone

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
        "voltage": 0.0,
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
        self.readback_sequence = []
        self.turn_on_exception = None

    async def get_all_live(self):
        self.calls.append("get_all_live")
        data = dict(self.live)
        if self.readback_sequence:
            data.update(self.readback_sequence.pop(0))
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
        if self.turn_on_exception is not None:
            raise self.turn_on_exception
        if self.fail_method == "turn_on":
            return False
        self.live["switch"] = "on"
        self.live["voltage"] = self.live["set_voltage"]
        self.live["current"] = self.live["set_current"]
        return True

    async def turn_off(self, entity_id=None):
        self.calls.append("turn_off")
        if self.fail_method == "turn_off":
            return False
        self.live["switch"] = "off"
        self.live["voltage"] = 0.0
        self.live["current"] = 0.0
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

    def test_any_target_above_17_5v_is_rejected(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state())
        assert telemetry is not None
        decision = supervisor.preflight(
            OutputRequest(17.51, 3.0, 17.6, 3.1, recipe_voltage_ceiling_v=17.51),
            telemetry,
        )
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.REQUEST_OVER_ABSOLUTE_CEILING, decision.violations)

    def test_recipe_ceiling_is_not_same_as_global_absolute_ceiling(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state())
        assert telemetry is not None
        decision = supervisor.preflight(
            OutputRequest(16.4, 2.0, 16.5, 2.1, recipe_voltage_ceiling_v=16.3), telemetry
        )
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.REQUEST_OVER_RECIPE_CEILING, decision.violations)

    def test_input_voltage_is_optional_psu_health_telemetry_not_charge_authority(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(input_voltage=0.0))
        assert telemetry is not None
        decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry)
        self.assertTrue(decision.allowed)
        self.assertNotIn(SafetyViolation.INPUT_VOLTAGE_LOW, decision.violations)
        self.assertIsNotNone(snapshot_from_live(live_state(input_voltage=None)))

    def test_missing_external_temperature_fails_closed(self):
        self.assertIsNone(snapshot_from_live(live_state(temp_ext=None)))

    def test_missing_internal_temperature_fails_closed(self):
        self.assertIsNone(snapshot_from_live(live_state(temp_int="unavailable")))

    def test_hot_power_supply_blocks_enable(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(temp_int=55.0))
        assert telemetry is not None
        decision = supervisor.preflight(
            OutputRequest(16.3, 2.0, 16.4, 2.1, recipe_voltage_ceiling_v=16.3), telemetry
        )
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.POWER_SUPPLY_TOO_HOT, decision.violations)

    def test_raw_opp_status_is_a_real_protection_trip(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(protection_code=3))
        assert telemetry is not None
        self.assertEqual(telemetry.protection_status.value, "opp")
        decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry)
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.PROTECTION_ALREADY_TRIPPED, decision.violations)

    def test_unknown_raw_protection_code_fails_closed(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(protection_code=7))
        assert telemetry is not None
        decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry)
        self.assertIn(SafetyViolation.UNKNOWN_HARDWARE_PROTECTION, decision.violations)

    def test_legacy_both_ovp_and_ocp_is_unknown_not_two_independent_bits(self):
        telemetry = snapshot_from_live(live_state(ovp_triggered="on", ocp_triggered="on"))
        assert telemetry is not None
        self.assertTrue(telemetry.protection_unknown)

    def test_boot_power_or_take_out_blocks_managed_enable_when_exposed(self):
        supervisor = SafetySupervisor()
        for key in ("boot_power", "take_out"):
            telemetry = snapshot_from_live(live_state(**{key: "on"}))
            assert telemetry is not None
            decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry)
            self.assertIn(SafetyViolation.UNSAFE_HARDWARE_CONFIGURATION, decision.violations)

    def test_battery_mode_is_observational_not_preflight_permission(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(battery_mode="off"))
        assert telemetry is not None
        decision = supervisor.preflight(OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry)
        self.assertTrue(decision.allowed)

    def test_stale_critical_ha_metadata_fails_closed(self):
        old = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
        live = live_state()
        keys = [
            "battery_voltage", "voltage", "current", "temp_ext", "temp_int", "switch",
            "ovp_triggered", "ocp_triggered", "set_voltage", "set_current", "ovp", "ocp",
        ]
        live["_meta"] = {key: {"status": "ok", "last_updated": old} for key in keys}
        self.assertIsNone(snapshot_from_live(live))

    def test_readback_detail_identifies_exact_values(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(set_voltage=14.0, ocp=None))
        assert telemetry is not None
        decision = supervisor.verify_programmed(OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry)
        self.assertFalse(decision.allowed)
        self.assertIn("set_voltage actual=14.000 expected=16.300", decision.detail)
        self.assertIn("ocp=missing expected=2.100", decision.detail)

    def test_post_enable_requires_measured_output_voltage(self):
        supervisor = SafetySupervisor()
        telemetry = snapshot_from_live(live_state(switch="on", voltage=None, current=2.0))
        assert telemetry is not None
        decision = supervisor.verify_live_output(
            OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3), telemetry
        )
        self.assertFalse(decision.allowed)
        self.assertIn(SafetyViolation.TELEMETRY_INVALID, decision.violations)


class SafeOutputCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.request = OutputRequest(16.3, 2.0, 16.4, 2.1, 16.3)

    def test_default_programmed_readback_window_is_ten_seconds(self):
        self.assertEqual(SafeOutputCoordinator(FakeAdapter()).readback_timeout_s, 10.0)

    def test_happy_path_programs_protections_before_output(self):
        adapter = FakeAdapter()
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertTrue(result.enabled)
        self.assertEqual(
            adapter.calls,
            ["get_all_live", "set_ovp", "set_ocp", "set_voltage", "set_current", "get_all_live", "turn_on", "get_all_live"],
        )

    def test_programming_failure_forces_output_off(self):
        adapter = FakeAdapter()
        adapter.fail_method = "set_current"
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.PROGRAMMING_FAILED, result.violations)
        self.assertIn("turn_off", adapter.calls)
        self.assertNotIn("turn_on", adapter.calls)

    def test_readback_mismatch_forces_output_off_with_detail(self):
        adapter = FakeAdapter()
        adapter.readback_override = {"set_voltage": 14.0}
        result = asyncio.run(SafeOutputCoordinator(adapter, readback_timeout_s=0.0).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.READBACK_MISMATCH, result.violations)
        self.assertIn("turn_off", adapter.calls)

    def test_programmed_readback_polls_through_stale_ha_state(self):
        adapter = FakeAdapter()
        adapter.readback_sequence = [
            {},
            {"set_voltage": 14.0, "set_current": 1.0, "ovp": 14.1, "ocp": 1.1},
            {"set_voltage": 14.0, "set_current": 1.0, "ovp": 14.1, "ocp": 1.1},
        ]
        result = asyncio.run(
            SafeOutputCoordinator(adapter, readback_timeout_s=0.2, readback_poll_interval_s=0.01).enable(self.request)
        )
        self.assertTrue(result.enabled)
        self.assertGreaterEqual(adapter.calls.count("get_all_live"), 4)

    def test_delayed_canonical_readback_is_allowed_inside_extended_window(self):
        class DelayedReadbackAdapter(FakeAdapter):
            async def get_all_live(self):
                if self.calls.count("get_all_live") == 1:
                    await asyncio.sleep(7.5)
                return await super().get_all_live()

        adapter = DelayedReadbackAdapter()
        stamp = datetime.now(timezone.utc).isoformat()
        adapter.live.update({
            "set_current_readback_v2": 0.2,
            "protection_code": 0,
            "_meta": {
                key: {"status": "ok", "last_reported": stamp, "last_updated": stamp}
                for key in (
                    "battery_voltage", "voltage", "current", "temp_ext", "temp_int",
                    "switch", "protection_code", "set_voltage", "set_current", "ovp", "ocp",
                    "set_current_readback_v2",
                )
            },
        })
        fresh_readback = {
            "set_voltage": 16.3,
            "set_current": 2.0,
            "set_current_readback_v2": 2.0,
            "ovp": 16.4,
            "ocp": 2.1,
        }
        adapter.readback_sequence = [{}, fresh_readback, fresh_readback]
        result = asyncio.run(
            SafeOutputCoordinator(
                adapter, readback_timeout_s=10.0, readback_poll_interval_s=0.01
            ).enable(self.request)
        )
        self.assertTrue(result.enabled, result.detail)
        self.assertEqual(adapter.calls.count("turn_on"), 1)

    def test_missing_programmed_telemetry_is_not_reported_as_mismatch(self):
        adapter = FakeAdapter()
        adapter.readback_override = {"battery_voltage": None}
        result = asyncio.run(SafeOutputCoordinator(adapter, readback_timeout_s=0.0).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.TELEMETRY_INVALID, result.violations)
        self.assertNotIn(SafetyViolation.READBACK_MISMATCH, result.violations)

    def test_output_enable_exception_preserves_root_cause(self):
        adapter = FakeAdapter()
        adapter.turn_on_exception = RuntimeError("edge safety lease arm failed: edge lease telemetry is missing/unavailable")
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.OUTPUT_ENABLE_FAILED, result.violations)
        self.assertIn("edge safety lease arm failed", result.detail)
        self.assertIn("turn_off", adapter.calls)

    def test_output_already_on_is_never_reprogrammed_in_enable_path(self):
        adapter = FakeAdapter()
        adapter.live["switch"] = "on"
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.OUTPUT_ALREADY_ON, result.violations)
        self.assertEqual(adapter.calls, ["get_all_live"])

    def test_post_enable_input_drop_is_diagnostic_only(self):
        adapter = FakeAdapter()
        original_turn_on = adapter.turn_on

        async def turn_on_then_drop(entity_id=None):
            result = await original_turn_on(entity_id)
            adapter.live["input_voltage"] = 55.0
            return result

        adapter.turn_on = turn_on_then_drop
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertTrue(result.enabled)
        self.assertEqual(adapter.live["switch"], "on")

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

    def test_post_enable_measured_voltage_over_recipe_forces_output_off(self):
        adapter = FakeAdapter()
        original_turn_on = adapter.turn_on

        async def turn_on_then_overshoot(entity_id=None):
            result = await original_turn_on(entity_id)
            adapter.live["voltage"] = 16.7
            return result

        adapter.turn_on = turn_on_then_overshoot
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.MEASURED_OUTPUT_OVER_LIMIT, result.violations)
        self.assertEqual(adapter.live["switch"], "off")

    def test_post_enable_telemetry_exception_forces_output_off(self):
        adapter = FakeAdapter()
        original_get = adapter.get_all_live

        async def get_then_fail_after_on():
            if adapter.live["switch"] == "on":
                adapter.calls.append("get_all_live")
                raise RuntimeError("synthetic post-enable HA loss")
            return await original_get()

        adapter.get_all_live = get_then_fail_after_on
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(self.request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.POST_ENABLE_VERIFY_FAILED, result.violations)
        self.assertIn(SafetyViolation.TELEMETRY_INVALID, result.violations)
        self.assertEqual(adapter.live["switch"], "off")
        self.assertIn("turn_off", adapter.calls)

    def test_measured_current_above_12a_working_ceiling_forces_output_off(self):
        request = OutputRequest(17.0, 12.0, 17.1, 12.2, 17.5)
        adapter = FakeAdapter()
        original_turn_on = adapter.turn_on

        async def turn_on_then_overcurrent(entity_id=None):
            result = await original_turn_on(entity_id)
            adapter.live["current"] = 12.10
            return result

        adapter.turn_on = turn_on_then_overcurrent
        result = asyncio.run(SafeOutputCoordinator(adapter).enable(request))
        self.assertFalse(result.enabled)
        self.assertIn(SafetyViolation.CURRENT_OVER_ABSOLUTE_LIMIT, result.violations)
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


if __name__ == "__main__":
    unittest.main()
