import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from diagnostic_probe import ControlledCurrentProbe, ProbePlan


class FakeProbeHass:
    def __init__(self):
        self.set_current_value = 7.0
        self.output_on = True
        self.restore_fails = False
        self.off_fails = False
        self.off_raises = False
        self.off_calls = 0

    async def get_all_live(self):
        current = self.set_current_value
        voltage = 14.10 if current > 5.0 else 14.04
        measured_current = 7.0 if current > 5.0 else 3.0
        return {
            "switch": "on" if self.output_on else "off",
            "protection_code": 0,
            "temp_ext": 25.0,
            "battery_voltage": voltage,
            "current": measured_current,
            "set_current": current,
            "ocp": 7.1,
        }

    async def set_current(self, value):
        if self.restore_fails and value > 5.0:
            return False
        self.set_current_value = float(value)
        return True

    async def turn_off(self):
        self.off_calls += 1
        if self.off_raises:
            raise RuntimeError("synthetic OFF failure")
        if self.off_fails:
            return False
        self.output_on = False
        return True


class DiagnosticProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_only_reduces_current_and_restores_original(self):
        hass = FakeProbeHass()
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=3.0, settle_s=0.0, sample_count=3, sample_interval_s=0.01)
        with patch("diagnostic_probe.asyncio.sleep", new=AsyncMock()):
            result = await runner.run(
                battery_id="efb-1",
                stage="Main Charge",
                connection_id="session-A",
                plan=plan,
            )
        self.assertTrue(result.ok)
        assert result.probe is not None
        self.assertAlmostEqual(result.probe.dynamic_loop_mohm or 0.0, 15.0, places=3)
        self.assertAlmostEqual(hass.set_current_value, 7.0)
        self.assertEqual(hass.off_calls, 0)

    async def test_probe_rejects_non_reducing_step(self):
        hass = FakeProbeHass()
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=7.0, settle_s=0.0, sample_count=2, sample_interval_s=0.01)
        result = await runner.run(
            battery_id="efb-1",
            stage="Main Charge",
            connection_id="session-A",
            plan=plan,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "probe_must_reduce_current")
        self.assertEqual(hass.off_calls, 0)

    async def test_restore_failure_forces_output_off(self):
        hass = FakeProbeHass()
        hass.restore_fails = True
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=3.0, settle_s=0.0, sample_count=2, sample_interval_s=0.01)
        with patch("diagnostic_probe.asyncio.sleep", new=AsyncMock()):
            result = await runner.run(
                battery_id="efb-1",
                stage="Main Charge",
                connection_id="session-A",
                plan=plan,
            )
        self.assertFalse(result.ok)
        self.assertTrue(result.output_forced_off)
        self.assertEqual(result.reason, "original_current_restore_unconfirmed")
        self.assertEqual(hass.off_calls, 1)
        self.assertFalse(hass.output_on)

    async def test_restore_and_off_failure_is_not_reported_as_forced_off(self):
        hass = FakeProbeHass()
        hass.restore_fails = True
        hass.off_fails = True
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=3.0, settle_s=0.0, sample_count=2, sample_interval_s=0.01)
        with patch("diagnostic_probe.asyncio.sleep", new=AsyncMock()):
            result = await runner.run(
                battery_id="efb-1",
                stage="Main Charge",
                connection_id="session-A",
                plan=plan,
            )
        self.assertFalse(result.ok)
        self.assertFalse(result.output_forced_off)
        self.assertIn("output_off_unconfirmed", result.reason)
        self.assertEqual(hass.off_calls, 1)
        self.assertTrue(hass.output_on)

    async def test_restore_and_off_exception_is_not_suppressed_into_false_success(self):
        hass = FakeProbeHass()
        hass.restore_fails = True
        hass.off_raises = True
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=3.0, settle_s=0.0, sample_count=2, sample_interval_s=0.01)
        with patch("diagnostic_probe.asyncio.sleep", new=AsyncMock()):
            result = await runner.run(
                battery_id="efb-1",
                stage="Main Charge",
                connection_id="session-A",
                plan=plan,
            )
        self.assertFalse(result.ok)
        self.assertFalse(result.output_forced_off)
        self.assertIn("output_off_unconfirmed", result.reason)
        self.assertTrue(hass.output_on)

    async def test_cancellation_after_step_restores_original_before_escaping(self):
        hass = FakeProbeHass()
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=3.0, settle_s=0.0, sample_count=2, sample_interval_s=0.01)
        runner._sample_medians = AsyncMock(
            side_effect=[(14.10, 7.0), asyncio.CancelledError()]
        )

        with self.assertRaises(asyncio.CancelledError):
            await runner.run(
                battery_id="efb-1",
                stage="Main Charge",
                connection_id="session-A",
                plan=plan,
            )

        self.assertAlmostEqual(hass.set_current_value, 7.0)
        self.assertEqual(hass.off_calls, 0)
        self.assertTrue(hass.output_on)

    async def test_cancellation_restore_failure_forces_off_before_escaping(self):
        hass = FakeProbeHass()
        hass.restore_fails = True
        runner = ControlledCurrentProbe(hass)
        plan = ProbePlan(step_current_a=3.0, settle_s=0.0, sample_count=2, sample_interval_s=0.01)
        runner._sample_medians = AsyncMock(
            side_effect=[(14.10, 7.0), asyncio.CancelledError()]
        )

        with self.assertRaises(asyncio.CancelledError):
            await runner.run(
                battery_id="efb-1",
                stage="Main Charge",
                connection_id="session-A",
                plan=plan,
            )

        self.assertEqual(hass.off_calls, 1)
        self.assertFalse(hass.output_on)

    async def test_hot_battery_blocks_probe_before_any_setpoint_change(self):
        hass = FakeProbeHass()
        original = hass.get_all_live

        async def hot_live():
            live = await original()
            live["temp_ext"] = 35.0
            return live

        hass.get_all_live = hot_live
        runner = ControlledCurrentProbe(hass)
        result = await runner.run(
            battery_id="efb-1",
            stage="Main Charge",
            connection_id="session-A",
            plan=ProbePlan(step_current_a=3.0),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "battery_temperature_not_suitable")
        self.assertAlmostEqual(hass.set_current_value, 7.0)


if __name__ == "__main__":
    unittest.main()
