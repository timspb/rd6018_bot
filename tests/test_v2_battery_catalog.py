import os
import tempfile
import unittest

import database
from battery_registry import upsert_battery
from pb_domain import BatteryChemistry, BatteryIdentity, BatteryLifecycle
from v2_battery_catalog import list_batteries


class V2BatteryCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "catalog.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def test_catalog_is_most_recent_first_and_limited(self):
        await upsert_battery(
            BatteryIdentity("old-agm", BatteryChemistry.AGM, 70, manufacturer="Old"),
            BatteryLifecycle(),
            updated_at=10.0,
        )
        await upsert_battery(
            BatteryIdentity("new-efb", BatteryChemistry.EFB, 80, manufacturer="New"),
            BatteryLifecycle(),
            updated_at=20.0,
        )

        records = await list_batteries(limit=1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].identity.battery_id, "new-efb")

    async def test_empty_catalog_is_valid(self):
        self.assertEqual(await list_batteries(), [])


if __name__ == "__main__":
    unittest.main()
