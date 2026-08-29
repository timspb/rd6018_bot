import unittest
from unittest.mock import AsyncMock, patch

from battery_registry import BatteryRecord
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle, ChargeIntent
from recovery_orchestrator import RecoveryOrchestrator
from safe_output import EnableResult


class FakeOutput:
    def __init__(self, enabled=True):
        self.safe_calls = []
        self.turn_off = AsyncMock(return_value=True)
        self.enabled = enabled
    async def safe_enable_output(self, **kwargs):
        self.safe_calls.append(kwargs)
        return EnableResult(enabled=self.enabled, detail="" if self.enabled else "blocked")


class FakeRuntime:
    def __init__(self, start_error=None):
        self.active = False
        self.started = []
        self.start_error = start_error
        self.observations = []
        self.aborted = False
    async def start(self, **kwargs):
        if self.start_error:
            raise self.start_error
        self.started.append(kwargs)
        self.active = True
    def observe(self, **kwargs):
        self.observations.append(kwargs)
        return kwargs
    async def complete(self, **kwargs):
        self.active = False
        return kwargs
    def abort(self):
        self.active = False
        self.aborted = True


class RecoveryOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def _record(self, chemistry=BatteryChemistry.AGM, condition=BatteryCondition.REHYDRATED):
        return BatteryRecord(
            identity=BatteryIdentity("bat-1", chemistry, 70),
            lifecycle=BatteryLifecycle(condition=condition),
        )

    async def test_unknown_battery_does_not_touch_hardware(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=None)):
            result = await orchestrator.start_target(
                battery_id="missing", intent=ChargeIntent.RECOVERY, stage="Mix Mode",
                target_voltage_v=16.3, target_current_a=2.0, started_at=0,
            )
        self.assertFalse(result.started)
        self.assertEqual(output.safe_calls, [])
        self.assertEqual(runtime.started, [])

    async def test_diagnostic_agm_hv_is_rejected_before_hardware(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=self._record())):
            result = await orchestrator.start_target(
                battery_id="bat-1", intent=ChargeIntent.DIAGNOSTIC, stage="Mix Mode",
                target_voltage_v=16.3, target_current_a=2.0, started_at=0,
            )
        self.assertFalse(result.started)
        self.assertEqual(output.safe_calls, [])
        self.assertEqual(runtime.started, [])

    async def test_normal_agm_standard_mix_is_authorized(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=self._record())):
            result = await orchestrator.start_target(
                battery_id="bat-1", intent=ChargeIntent.NORMAL, stage="Mix Mode",
                target_voltage_v=16.3, target_current_a=2.0, started_at=12,
            )
        self.assertTrue(result.started)
        self.assertEqual(len(output.safe_calls), 1)
        self.assertEqual(len(runtime.started), 1)

    async def test_recovery_starts_output_then_runtime_with_registry_condition(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        record = self._record()
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=record)):
            result = await orchestrator.start_target(
                battery_id="bat-1", intent=ChargeIntent.RECOVERY, stage="Mix Mode",
                target_voltage_v=16.3, target_current_a=2.0, started_at=123,
            )
        self.assertTrue(result.started)
        self.assertEqual(len(output.safe_calls), 1)
        self.assertEqual(len(runtime.started), 1)
        self.assertEqual(runtime.started[0]["condition_before"], BatteryCondition.REHYDRATED)
        self.assertEqual(runtime.started[0]["started_at"], 123.0)

    async def test_runtime_start_failure_forces_output_off(self):
        output = FakeOutput()
        runtime = FakeRuntime(start_error=RuntimeError("tracker init failed"))
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=self._record())):
            with self.assertRaises(RuntimeError):
                await orchestrator.start_target(
                    battery_id="bat-1", intent=ChargeIntent.RECOVERY, stage="Mix Mode",
                    target_voltage_v=16.3, target_current_a=2.0, started_at=123,
                )
        output.turn_off.assert_awaited_once()

    async def test_hardware_rejection_prevents_runtime_start(self):
        output, runtime = FakeOutput(enabled=False), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=self._record())):
            result = await orchestrator.start_target(
                battery_id="bat-1", intent=ChargeIntent.RECOVERY, stage="Mix Mode",
                target_voltage_v=16.3, target_current_a=2.0, started_at=123,
            )
        self.assertFalse(result.started)
        self.assertEqual(runtime.started, [])


if __name__ == "__main__":
    unittest.main()
