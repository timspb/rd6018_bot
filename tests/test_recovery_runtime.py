import unittest
from unittest.mock import AsyncMock, patch

from pb_domain import BatteryCondition, ChargeIntent
from recovery_policy import RecoveryDecision
from recovery_runtime import RecoveryRuntime, _registry_battery_exists


class RecoveryRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_registry_lookup_initializes_schema_first(self):
        order = []

        async def init_registry():
            order.append("init")

        async def get_registered(_battery_id):
            order.append("get")
            return object()

        with patch("recovery_runtime.init_battery_registry", side_effect=init_registry), patch(
            "recovery_runtime.get_battery", side_effect=get_registered
        ):
            exists = await _registry_battery_exists("bat-1")

        self.assertTrue(exists)
        self.assertEqual(order, ["init", "get"])

    async def test_unknown_battery_is_rejected(self):
        async def missing(_battery_id):
            return False

        runtime = RecoveryRuntime(battery_exists=missing)
        with self.assertRaises(KeyError):
            await runtime.start(
                battery_id="missing",
                started_at=0.0,
                intent=ChargeIntent.RECOVERY,
            )

    async def test_live_observation_returns_policy_decision_and_persists_once(self):
        persisted = []

        async def exists(_battery_id):
            return True

        async def persist(evidence):
            persisted.append(evidence)
            return 1

        runtime = RecoveryRuntime(battery_exists=exists, persist_cycle=persist)
        await runtime.start(
            battery_id="efb-1",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.REHYDRATED,
        )

        samples = [
            (0, 16.35, 0.40, 25.0),
            (120, 16.45, 0.20, 25.1),
            (240, 16.48, 0.20, 25.1),
            (360, 16.49, 0.28, 25.2),
            (420, 16.49, 0.29, 25.2),
            (480, 16.49, 0.30, 25.2),
        ]
        last = None
        for ts, voltage, current, temp in samples:
            last = runtime.observe(
                timestamp_s=ts,
                stage="Mix Mode",
                voltage_v=voltage,
                current_a=current,
                temp_c=temp,
                is_cv=True,
                target_voltage_v=16.5,
                ah=5.0 + ts / 36000.0,
            )

        self.assertIsNotNone(last)
        self.assertEqual(last.decision.decision, RecoveryDecision.FINISH_STAGE)
        self.assertAlmostEqual(last.evidence.hv_imin_a, 0.20)

        evidence = await runtime.complete(
            completed_at=600.0,
            outcome="completed",
            measured_capacity_ah=48.0,
        )
        self.assertFalse(runtime.active)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0], evidence)
        self.assertEqual(evidence.condition_before, BatteryCondition.REHYDRATED)
        self.assertAlmostEqual(evidence.measured_capacity_ah, 48.0)

    async def test_thermal_acceleration_is_surfaceable_without_hardware_dependency(self):
        async def exists(_battery_id):
            return True

        async def persist(_evidence):
            return 1

        runtime = RecoveryRuntime(battery_exists=exists, persist_cycle=persist)
        await runtime.start(
            battery_id="agm-1",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
        )

        points = [
            (0, 16.20, 0.20, 25.0),
            (120, 16.28, 0.20, 25.1),
            (240, 16.30, 0.28, 26.0),
            (360, 16.31, 0.30, 27.2),
        ]
        result = None
        for ts, voltage, current, temp in points:
            result = runtime.observe(
                timestamp_s=ts,
                stage="recovery",
                voltage_v=voltage,
                current_a=current,
                temp_c=temp,
                is_cv=True,
                target_voltage_v=16.3,
                output_is_on=True,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.decision.decision, RecoveryDecision.PAUSE_THERMAL)

    async def test_double_start_and_observe_without_session_are_rejected(self):
        async def exists(_battery_id):
            return True

        runtime = RecoveryRuntime(battery_exists=exists)
        with self.assertRaises(RuntimeError):
            runtime.observe(
                timestamp_s=0,
                stage="Main Charge",
                voltage_v=14.0,
                current_a=1.0,
                temp_c=25.0,
                is_cv=False,
            )

        await runtime.start(
            battery_id="bat-1",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
        )
        with self.assertRaises(RuntimeError):
            await runtime.start(
                battery_id="bat-2",
                started_at=1.0,
                intent=ChargeIntent.RECOVERY,
            )


if __name__ == "__main__":
    unittest.main()
