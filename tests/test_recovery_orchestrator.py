import unittest
from unittest.mock import AsyncMock, patch

from battery_registry import BatteryRecord
from pb_domain import BatteryChemistry, BatteryCondition, BatteryIdentity, BatteryLifecycle, ChargeIntent
from recovery_orchestrator import RecoveryOrchestrator, RecoveryOutputOffUnconfirmed
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

    async def _start(self, orchestrator, *, intent=ChargeIntent.RECOVERY):
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=self._record())):
            return await orchestrator.start_target(
                battery_id="bat-1",
                intent=intent,
                stage="Mix Mode",
                target_voltage_v=16.3,
                target_current_a=2.0,
                started_at=123,
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
        self.assertTrue(orchestrator.containment_active)
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
        self.assertTrue(orchestrator.containment_active)
        self.assertEqual(len(output.safe_calls), 1)
        self.assertEqual(len(runtime.started), 1)
        self.assertEqual(runtime.started[0]["condition_before"], BatteryCondition.REHYDRATED)
        self.assertEqual(runtime.started[0]["started_at"], 123.0)

    async def test_runtime_start_failure_rethrows_original_only_after_confirmed_off(self):
        output = FakeOutput()
        runtime = FakeRuntime(start_error=RuntimeError("tracker init failed"))
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with self.assertRaisesRegex(RuntimeError, "tracker init failed"):
            await self._start(orchestrator)
        output.turn_off.assert_awaited_once()
        self.assertFalse(orchestrator.containment_active)
        self.assertFalse(runtime.active)

    async def test_runtime_start_failure_with_unconfirmed_off_retains_containment(self):
        output = FakeOutput()
        output.turn_off.return_value = False
        runtime = FakeRuntime(start_error=RuntimeError("tracker init failed"))
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)

        with self.assertRaisesRegex(RecoveryOutputOffUnconfirmed, "OFF was not confirmed"):
            await self._start(orchestrator)

        self.assertTrue(orchestrator.containment_active)
        self.assertFalse(runtime.active)
        output.turn_off.assert_awaited_once()

        # An uncertain previously enabled output may never be followed by another start.
        second = await self._start(orchestrator)
        self.assertFalse(second.started)
        self.assertIn("containment", second.reason)
        self.assertEqual(len(output.safe_calls), 1)

    async def test_runtime_start_failure_with_off_exception_retains_containment(self):
        output = FakeOutput()
        output.turn_off.side_effect = RuntimeError("HA unavailable")
        runtime = FakeRuntime(start_error=RuntimeError("tracker init failed"))
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)

        with self.assertRaisesRegex(RecoveryOutputOffUnconfirmed, "HA unavailable"):
            await self._start(orchestrator)

        self.assertTrue(orchestrator.containment_active)
        self.assertFalse(runtime.active)

    async def test_abort_clears_software_authority_only_after_confirmed_off(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        result = await self._start(orchestrator)
        self.assertTrue(result.started)

        await orchestrator.abort()

        output.turn_off.assert_awaited_once()
        self.assertTrue(runtime.aborted)
        self.assertFalse(runtime.active)
        self.assertFalse(orchestrator.containment_active)

    async def test_abort_unconfirmed_off_keeps_runtime_and_authorization_active(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        result = await self._start(orchestrator)
        self.assertTrue(result.started)
        output.turn_off.return_value = False

        with self.assertRaisesRegex(RecoveryOutputOffUnconfirmed, "OFF was not confirmed"):
            await orchestrator.abort()

        self.assertFalse(runtime.aborted)
        self.assertTrue(runtime.active)
        self.assertTrue(orchestrator.containment_active)

    async def test_abort_off_exception_keeps_runtime_and_authorization_active(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        result = await self._start(orchestrator)
        self.assertTrue(result.started)
        output.turn_off.side_effect = RuntimeError("link down")

        with self.assertRaisesRegex(RecoveryOutputOffUnconfirmed, "link down"):
            await orchestrator.abort()

        self.assertFalse(runtime.aborted)
        self.assertTrue(runtime.active)
        self.assertTrue(orchestrator.containment_active)

    async def test_abort_without_output_command_is_explicit_software_only_retire(self):
        output, runtime = FakeOutput(), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        result = await self._start(orchestrator)
        self.assertTrue(result.started)

        await orchestrator.abort(turn_output_off=False)

        output.turn_off.assert_not_awaited()
        self.assertTrue(runtime.aborted)
        self.assertFalse(orchestrator.containment_active)

    async def test_hardware_rejection_prevents_runtime_start(self):
        output, runtime = FakeOutput(enabled=False), FakeRuntime()
        orchestrator = RecoveryOrchestrator(output, runtime=runtime)
        with patch("recovery_orchestrator.get_battery", AsyncMock(return_value=self._record())):
            result = await orchestrator.start_target(
                battery_id="bat-1", intent=ChargeIntent.RECOVERY, stage="Mix Mode",
                target_voltage_v=16.3, target_current_a=2.0, started_at=123,
            )
        self.assertFalse(result.started)
        self.assertFalse(orchestrator.containment_active)
        self.assertEqual(runtime.started, [])


if __name__ == "__main__":
    unittest.main()
