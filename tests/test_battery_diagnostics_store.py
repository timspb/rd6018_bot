import os
import tempfile
import unittest

import database
from battery_diagnostics import DynamicLoopProbe, SpecificGravityMeasurement
from battery_diagnostics_store import (
    init_battery_diagnostics_store,
    list_dynamic_loop_probes,
    list_specific_gravity,
    record_dynamic_loop_probe,
    record_specific_gravity,
)
from battery_registry import init_battery_registry, upsert_battery
from pb_domain import BatteryChemistry, BatteryIdentity, BatteryLifecycle


class BatteryDiagnosticsStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        await init_battery_registry()
        await init_battery_diagnostics_store()
        self.identity = BatteryIdentity("flooded-70", BatteryChemistry.FLOODED, 70)
        await upsert_battery(self.identity, BatteryLifecycle(), updated_at=1.0)

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def test_specific_gravity_round_trip_preserves_cell_positions(self):
        measurement = SpecificGravityMeasurement.from_iterable(
            battery_id=self.identity.battery_id,
            measured_at=100.0,
            temperature_c=22.5,
            context="diagnostic_rest",
            cells=(1.27, 1.268, None, 1.265, 1.269, 1.267),
            notes="cell 3 inaccessible",
        )
        row_id = await record_specific_gravity(measurement)
        self.assertGreater(row_id, 0)
        stored = await list_specific_gravity(self.identity.battery_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].cells[2], None)
        self.assertEqual(stored[0].context, "diagnostic_rest")
        self.assertAlmostEqual(stored[0].temperature_c or 0.0, 22.5)

    async def test_dynamic_probe_round_trip_preserves_connection_identity(self):
        probe = DynamicLoopProbe(
            battery_id=self.identity.battery_id,
            measured_at=200.0,
            stage="Main Charge",
            baseline_voltage_v=14.10,
            baseline_current_a=7.0,
            stepped_voltage_v=14.04,
            stepped_current_a=3.0,
            connection_id="clip-session-A",
        )
        row_id = await record_dynamic_loop_probe(probe)
        self.assertGreater(row_id, 0)
        stored = await list_dynamic_loop_probes(self.identity.battery_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].connection_id, "clip-session-A")
        self.assertAlmostEqual(stored[0].dynamic_loop_mohm or 0.0, 15.0)

    async def test_unknown_battery_is_rejected(self):
        with self.assertRaises(KeyError):
            await record_specific_gravity(
                SpecificGravityMeasurement.from_iterable(
                    battery_id="missing",
                    measured_at=100.0,
                    cells=(1.27, 1.27, 1.27, 1.27, 1.27, 1.27),
                )
            )


if __name__ == "__main__":
    unittest.main()
