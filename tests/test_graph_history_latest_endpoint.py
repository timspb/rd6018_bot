import unittest
from unittest.mock import patch

import aiosqlite
import database


class GraphHistoryEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("""
            CREATE TABLE sensor_history(
                id INTEGER PRIMARY KEY, timestamp TEXT,
                voltage REAL, current REAL, temp_ext REAL)
        """)
        await self.db.executemany(
            "INSERT INTO sensor_history (id,timestamp,voltage,current,temp_ext) VALUES (?,?,?,?,?)",
            [
                (idx + 1, f"2026-11-03T07:{idx:02d}:00Z", 14 + idx / 100, idx / 100, 25.0)
                for idx in range(12)
            ],
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()

    async def test_long_history_keeps_first_and_newest_samples(self):
        with patch("database.get_db", return_value=self.db):
            t, v, i, temp = await database.get_graph_data_with_temp(
                limit=5, since_timestamp=1793689200.0 - 3600
            )
        self.assertEqual(len(t), 5)
        self.assertEqual(t[0], "2026-11-03T07:00:00Z")
        self.assertEqual(t[-1], "2026-11-03T07:11:00Z")
        self.assertAlmostEqual(i[-1], 0.11)
        self.assertEqual(len(v), len(temp))

    async def test_single_point_requests_newest_not_oldest(self):
        with patch("database.get_db", return_value=self.db):
            t, _, _, _ = await database.get_graph_data_with_temp(
                limit=1, since_timestamp=1793689200.0 - 3600
            )
        self.assertEqual(t, ["2026-11-03T07:11:00Z"])
