"""B842 source-path coverage using synchronous sqlite3 behind an async fake port."""
from __future__ import annotations

import asyncio
import io
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import database
import graphing
from runtime.ui.components.hmi_navigation_keyboards import chart_query_params
from runtime.ui.components.operator_graph_policy import _graph_query_params


class _Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __await__(self):
        async def ready():
            return self
        return ready().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def fetchall(self):
        return self._cursor.fetchall()


class _SqliteHistoryFake:
    """Immediate sqlite3 implementation of the small aiosqlite surface in use."""
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE sensor_history (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, "
            "voltage REAL, current REAL, power REAL, temp_ext REAL)"
        )

    def execute(self, sql, parameters=()):
        return _Cursor(self.connection.execute(sql, parameters))

    def commit(self):
        self.connection.commit()
        async def done():
            return None
        return done()

    def close(self):
        self.connection.close()


class _ExternalGraphApp:
    CHART_RANGE_30M = "30m"
    CHART_RANGE_2H = "2h"
    CHART_RANGE_SESSION = "session"
    CHART_RANGE_DEFAULT = CHART_RANGE_2H
    CHART_RANGE_VALUES = {CHART_RANGE_30M, CHART_RANGE_2H, CHART_RANGE_SESSION}

    def __init__(self, now_s):
        self.user_chart_range = {7: self.CHART_RANGE_30M}
        self.charge_controller = type("Controller", (), {"is_active": False, "total_start_time": None})()
        self.manual_session_manager = type("Manual", (), {"is_active": False})()
        self.rd_control_mode_manager = type("Ownership", (), {"hands_off": True})()
        self.rd_live_mix_observer = None
        self._chart_range_for_user = lambda user_id: self.user_chart_range.get(user_id, self.CHART_RANGE_DEFAULT)
        self._chart_query_params = lambda user_id: chart_query_params(self, user_id, now_s=now_s)


class B842ExternalGraphHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db = _SqliteHistoryFake()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.now_s = self.now.timestamp()
        self.samples = [
            ("2026-11-24T01:00:00Z", 2.46, 1.56, 3.84, 29.0, 10 * 60),
            ("2026-11-24T01:00:20Z", 2.46, 1.56, 3.84, 29.0, 90 * 60),
            ("2026-11-24T01:00:40Z", 2.46, 1.56, 3.84, 29.0, 23 * 3600),
            ("2026-11-23T23:00:00Z", 2.46, 1.56, 3.84, 29.0, 25 * 3600),
        ]
        # Keep the test relative to now while exercising the production writer.
        self.timestamps = [
            (self.now - timedelta(seconds=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
            for _label, _v, _i, _p, _t, age in self.samples
        ]
        with patch("database.get_db", return_value=self.db):
            for ts, (_label, voltage, current, power, temp, _age) in zip(self.timestamps, self.samples):
                with patch("database._utc_iso", return_value=ts):
                    asyncio.run(database.add_record(voltage, current, power, temp))

    def tearDown(self):
        self.db.close()

    def _history_for(self, mode):
        app = _ExternalGraphApp(self.now_s)
        app.user_chart_range[7] = mode
        with patch("database.get_db", return_value=self.db):
            query_mode, since, limit = _graph_query_params(app, 7)
            history = asyncio.run(database.get_graph_data_with_temp(limit=limit, since_timestamp=since))
        return query_mode, since, limit, history

    def test_external_session_samples_reach_each_real_history_window(self):
        expectations = {
            "30m": (120, 1),
            "2h": (300, 2),
            # HANDS_OFF has no managed session start; the graph policy maps its
            # explicit Session choice to the existing truthful 24h history view.
            "session": (500, 3),
        }
        for mode, (expected_limit, expected_count) in expectations.items():
            with self.subTest(mode=mode):
                query_mode, since, limit, (times, volts, amps, temps) = self._history_for(mode)
                self.assertEqual(query_mode, mode)
                self.assertEqual(limit, expected_limit)
                self.assertEqual(len(times), expected_count)
                self.assertEqual((len(times), len(volts), len(amps), len(temps)),
                                 (expected_count,) * 4)
                self.assertTrue(all(value == 2.46 for value in volts))
                self.assertTrue(all(value == 1.56 for value in amps))
                self.assertTrue(all(value == 29.0 for value in temps))
                self.assertGreaterEqual(since, self.now_s - (86400 if mode == "session" else (1800 if mode == "30m" else 7200)) - 1)
                # Exercise the real renderer with rows obtained through the
                # real history query, rather than charting hard-coded arrays.
                image = graphing.generate_chart(times, volts, amps, temps)
                self.assertIsNotNone(image)
                self.assertTrue(image.getvalue().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_no_data_and_empty_timestamp_are_distinguishable_at_query_boundary(self):
        with patch("database.get_db", return_value=self.db):
            before = asyncio.run(database.get_graph_data_with_temp(limit=120, since_timestamp=self.now_s + 86400))
            self.assertEqual(before, ([], [], [], []))
            self.db.execute("UPDATE sensor_history SET timestamp = '' WHERE id = 1")
            # Without a range the legacy-history query can return an empty
            # timestamp; its paired values must not be assigned the current time.
            rows = asyncio.run(database.get_graph_data_with_temp(limit=120, since_timestamp=None))
        self.assertEqual(rows[0][0], "")
        self.assertIsNone(graphing.generate_chart(rows[0][:1], rows[1][:1], rows[2][:1], rows[3][:1]))
        mixed = graphing.generate_chart(rows[0], rows[1], rows[2], rows[3])
        self.assertIsNotNone(mixed)

    def test_recording_gap_is_not_filled_with_synthetic_measurements(self):
        # Only three external-session reports exist in the 24h window; the query
        # returns those samples and does not interpolate the missing hour.
        _mode, _since, _limit, (times, volts, amps, temps) = self._history_for("session")
        self.assertEqual(len(times), 3)
        self.assertEqual(len(volts), len(amps))
        self.assertEqual(len(amps), len(temps))

    def test_real_samples_with_a_gap_keep_their_source_times(self):
        from graphing import _parse_timestamps

        parsed = _parse_timestamps([self.timestamps[0], "", "malformed", self.timestamps[2]])
        self.assertIsNotNone(parsed[0])
        self.assertIsNone(parsed[1])
        self.assertIsNone(parsed[2])
        self.assertIsNotNone(parsed[3])


if __name__ == "__main__":
    unittest.main()
