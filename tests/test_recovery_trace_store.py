import json
import os
import tempfile
import unittest

import database
from pb_domain import BatteryCondition, ChargeIntent
from recovery_replay import replay_document
from recovery_trace_store import (
    TRACE_RETENTION_DAYS,
    TRACE_TABLE,
    cleanup_old_trace_points,
    export_replay_document,
    latest_trace_session_id,
    list_trace_sessions,
    record_shadow_trace,
)


class RecoveryTraceStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "trace.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    @staticmethod
    def _shadow(ts, *, voltage=14.8, current=0.6, temp=25.0, decision="continue"):
        return {
            "status": "ok",
            "decision": decision,
            "reason": "test",
            "legacy_effect": "continue",
            "disagreement": None,
            "trace_point": {
                "timestamp_s": ts,
                "stage": "Main Charge",
                "legacy_stage_after": "Main Charge",
                "voltage_v": voltage,
                "current_a": current,
                "temp_c": temp,
                "is_cv": True,
                "is_cc": False,
                "target_voltage_v": 14.8,
                "ah": 5.0 + ts / 36000.0,
                "output_on": True,
            },
        }

    async def _record(self, shadow):
        return await record_shadow_trace(
            session_id="efb-70:100000",
            started_at=100.0,
            battery_id="efb-70",
            battery_type="EFB",
            capacity_ah=70,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.SULFATED_SUSPECTED,
            shadow=shadow,
        )

    async def test_duplicate_poll_updates_same_trace_point(self):
        await self._record(self._shadow(100.0, current=0.60))
        await self._record(self._shadow(130.0, current=0.55))
        await self._record(self._shadow(130.0, current=0.54, decision="finish_stage"))

        sessions = await list_trace_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["sample_count"], 2)
        self.assertEqual(await latest_trace_session_id(), "efb-70:100000")

        document = await export_replay_document("efb-70:100000")
        trace = document["cycles"][0]["trace"]
        self.assertEqual(len(trace), 2)
        self.assertAlmostEqual(trace[-1]["current_a"], 0.54)
        self.assertEqual(document["trace_export"]["skipped_invalid_samples"], 0)

    async def test_exported_document_is_directly_replayable(self):
        await self._record(self._shadow(100.0, current=0.60))
        await self._record(self._shadow(160.0, current=0.45))
        await self._record(self._shadow(220.0, current=0.30))

        document = await export_replay_document("efb-70:100000")
        result = replay_document(document)
        self.assertEqual(len(result["cycles"]), 1)
        self.assertEqual(result["cycles"][0]["battery_id"], "efb-70")
        self.assertEqual(result["cycles"][0]["condition_before"], "sulfated_suspected")

    async def test_capture_freezes_reversal_threshold_semantics(self):
        relative = self._shadow(100.0)
        relative["metrics"] = {
            "current_min_a": 0.50,
            "delta_current_from_min_a": 0.16,
        }
        floor = self._shadow(130.0)
        floor["metrics"] = {
            "current_min_a": 0.05,
            "delta_current_from_min_a": 0.031,
        }
        await self._record(relative)
        await self._record(floor)

        db = await database.get_db()
        async with db.execute(
            f"SELECT shadow_json FROM {TRACE_TABLE} ORDER BY timestamp_s ASC"
        ) as cursor:
            rows = await cursor.fetchall()

        first = json.loads(rows[0]["shadow_json"])
        second = json.loads(rows[1]["shadow_json"])
        self.assertAlmostEqual(first["signal_config"]["reversal_ratio"], 0.30)
        self.assertAlmostEqual(first["signal_config"]["reversal_abs_floor_a"], 0.03)
        self.assertAlmostEqual(first["metrics"]["reversal_threshold_a"], 0.15)
        self.assertEqual(first["metrics"]["reversal_threshold_source"], "relative_to_imin")
        self.assertAlmostEqual(second["metrics"]["reversal_threshold_a"], 0.03)
        self.assertEqual(second["metrics"]["reversal_threshold_source"], "instrument_floor")

    async def test_invalid_sensor_sample_is_preserved_for_audit_but_skipped_by_replay(self):
        await self._record(self._shadow(100.0, current=0.60))
        bad = self._shadow(130.0)
        bad["status"] = "error"
        bad["trace_point"]["temp_c"] = None
        await self._record(bad)

        sessions = await list_trace_sessions()
        self.assertEqual(sessions[0]["sample_count"], 2)
        self.assertEqual(sessions[0]["shadow_error_count"], 1)

        document = await export_replay_document("efb-70:100000")
        self.assertEqual(document["trace_export"]["stored_samples"], 2)
        self.assertEqual(document["trace_export"]["replayable_samples"], 1)
        self.assertEqual(document["trace_export"]["skipped_invalid_samples"], 1)

    async def test_raw_trace_retention_is_bounded_without_touching_cycle_summaries(self):
        await self._record(self._shadow(100.0, current=0.60))
        await self._record(self._shadow(200.0, current=0.55))

        deleted = await cleanup_old_trace_points(
            now_s=100.0 + (TRACE_RETENTION_DAYS + 1) * 86400.0,
        )
        self.assertEqual(deleted, 2)
        self.assertEqual(await list_trace_sessions(), [])

    async def test_invalid_retention_window_is_rejected(self):
        with self.assertRaises(ValueError):
            await cleanup_old_trace_points(retention_days=0)

    async def test_missing_trace_point_is_rejected(self):
        with self.assertRaises(ValueError):
            await self._record({"status": "error"})


if __name__ == "__main__":
    unittest.main()
