import os
import tempfile
import unittest

import database
from battery_registry import (
    RecoveryCycleEvidence,
    get_battery,
    init_battery_registry,
    list_recovery_cycles,
    mark_battery_refilled,
    record_recovery_cycle,
    upsert_battery,
)
from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeIntent,
)


class BatteryRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        await init_battery_registry()

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def test_refill_and_recovery_cycles_are_longitudinal(self):
        identity = BatteryIdentity(
            "varta-agm-95",
            BatteryChemistry.AGM,
            95,
            manufacturer="Varta",
            model="95Ah AGM",
        )
        await upsert_battery(identity, BatteryLifecycle(), updated_at=100.0)
        record = await mark_battery_refilled(
            identity.battery_id,
            total_ml=240,
            per_cell_ml=40,
            timestamp=200.0,
        )
        self.assertEqual(record.lifecycle.condition, BatteryCondition.REHYDRATED)
        self.assertEqual(record.lifecycle.cycles_since_refill, 0)

        cycle_id = await record_recovery_cycle(
            RecoveryCycleEvidence(
                battery_id=identity.battery_id,
                started_at=300.0,
                completed_at=600.0,
                intent=ChargeIntent.RECOVERY,
                condition_before=BatteryCondition.REHYDRATED,
                main_target_v=14.7,
                main_imin_a=0.31,
                hv_target_v=16.3,
                hv_imin_a=0.70,
                hv_reversal_delta_a=0.22,
                temp_max_c=31.2,
                measured_capacity_ah=78.0,
                cca_a=650.0,
                internal_resistance_mohm=5.5,
                outcome="improved",
            )
        )
        self.assertGreater(cycle_id, 0)

        stored = await get_battery(identity.battery_id)
        assert stored is not None
        self.assertEqual(stored.lifecycle.cycles_since_refill, 1)
        self.assertEqual(stored.lifecycle.measured_capacity_ah, 78.0)
        self.assertEqual(stored.lifecycle.cca_a, 650.0)

        cycles = await list_recovery_cycles(identity.battery_id)
        self.assertEqual(len(cycles), 1)
        self.assertAlmostEqual(cycles[0].hv_imin_a or 0.0, 0.70)
        self.assertEqual(cycles[0].condition_before, BatteryCondition.REHYDRATED)

    async def test_cycle_for_unknown_battery_is_rejected(self):
        with self.assertRaises(KeyError):
            await record_recovery_cycle(
                RecoveryCycleEvidence(
                    battery_id="missing",
                    started_at=1.0,
                    completed_at=2.0,
                    intent=ChargeIntent.RECOVERY,
                )
            )


if __name__ == "__main__":
    unittest.main()
