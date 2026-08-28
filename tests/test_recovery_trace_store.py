import os
import tempfile
import unittest

import database
from pb_domain import BatteryCondition, ChargeIntent
from recovery_replay import replay_document
from recovery_trace_store import (
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

    async def test_missing_trace_point_is_rejected(self):
        with self.assertRaises(ValueError):
            await self._record({"status": "error"})


if __name__ == "__main__":
    unittest.main()
