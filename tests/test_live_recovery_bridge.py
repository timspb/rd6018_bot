import unittest

from live_recovery_bridge import LiveRecoveryBridge
from pb_domain import BatteryCondition, ChargeIntent
from recovery_runtime import RecoveryRuntime


class LiveRecoveryBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def _bridge(self):
        persisted = []

        async def exists(_battery_id):
            return True

        async def persist(evidence):
            persisted.append(evidence)
            return len(persisted)

        runtime = RecoveryRuntime(battery_exists=exists, persist_cycle=persist)
        bridge = LiveRecoveryBridge(runtime)
        await bridge.start(
            battery_id="efb-live",
            started_at=0.0,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.REHYDRATED,
        )
        return bridge, persisted

    async def test_bridge_is_non_actuating_and_does_not_mutate_actions(self):
        bridge, _ = await self._bridge()
        actions = {"set_voltage": 16.5, "set_current": 1.0}
        original = dict(actions)
        result = bridge.observe(
            timestamp_s=0,
            stage="Mix Mode",
            voltage_v=16.3,
            current_a=0.5,
            temp_c=25.0,
            is_cv=True,
            target_voltage_v=16.5,
            output_is_on=True,
            legacy_actions=actions,
        )
        self.assertEqual(actions, original)
        self.assertEqual(result.legacy_effect, "retarget")
        self.assertEqual(bridge.summary()["samples"], 1)

    async def test_clean_reversal_is_logged_as_legacy_disagreement(self):
        bridge, _ = await self._bridge()
        samples = [
            (0, 16.40, 0.40, 25.0),
            (120, 16.47, 0.20, 25.0),
            (240, 16.49, 0.20, 25.0),
            (300, 16.49, 0.27, 25.1),
            (360, 16.49, 0.28, 25.1),
            (420, 16.49, 0.29, 25.1),
        ]
        last = None
        for ts, voltage, current, temp in samples:
            last = bridge.observe(
                timestamp_s=ts,
                stage="Mix Mode",
                voltage_v=voltage,
                current_a=current,
                temp_c=temp,
                is_cv=True,
                target_voltage_v=16.5,
                output_is_on=True,
                legacy_actions={},
            )
        self.assertEqual(last.decision, "finish_stage")
        self.assertEqual(last.disagreement, "v2_would_finish_stage")
        self.assertEqual(
            bridge.summary()["disagreement_counts"]["v2_would_finish_stage"],
            1,
        )

    async def test_matching_legacy_stop_has_no_disagreement(self):
        bridge, _ = await self._bridge()
        result = bridge.observe(
            timestamp_s=0,
            stage="Main Charge",
            voltage_v=0.0,
            current_a=1.0,
            temp_c=25.0,
            is_cv=True,
            target_voltage_v=14.8,
            output_is_on=True,
            legacy_actions={"emergency_stop": True},
        )
        self.assertEqual(result.decision, "hold_output_off")
        self.assertIsNone(result.disagreement)

    async def test_complete_persists_exactly_one_cycle(self):
        bridge, persisted = await self._bridge()
        bridge.observe(
            timestamp_s=0,
            stage="Main Charge",
            voltage_v=14.6,
            current_a=0.7,
            temp_c=25.0,
            is_cv=True,
            target_voltage_v=14.8,
            output_is_on=True,
            legacy_actions={},
        )
        evidence = await bridge.complete(
            completed_at=600,
            outcome="shadow-complete",
            measured_capacity_ah=51.2,
        )
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0], evidence)
        self.assertFalse(bridge.active)
        self.assertAlmostEqual(evidence.measured_capacity_ah, 51.2)

    async def test_abort_discards_without_persistence(self):
        bridge, persisted = await self._bridge()
        bridge.abort()
        self.assertFalse(bridge.active)
        self.assertEqual(persisted, [])


if __name__ == "__main__":
    unittest.main()
