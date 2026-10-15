import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

import aiosqlite
from tools.voltage_relaxation_sidecar import (
    PassiveCollector, read_session, validated_session, SAFE_WAIT_STAGE,
)


def document(stage=SAFE_WAIT_STAGE, profile="EFB", session="s42"):
    return {
        "stage": stage, "profile": profile,
        "safe_wait_start": 9000.0, "safe_wait_next_stage": "Done",
        "v2_trace_session_id": session, "v2_battery_id": "test-battery",
    }


def canonical_live(voltage=13.2, output="off"):
    return {
        "battery_voltage": voltage, "current": 0, "switch": output, "temp_ext": 21.0,
        "_meta": {key: {"status": "ok", "age_s": 1.0}
                  for key in ("battery_voltage", "current", "switch")},
    }


class SessionTests(unittest.TestCase):
    def test_authentic_stage_and_source_recognized(self):
        parsed = validated_session(document(), file_mtime_s=9999, observed_at_s=10000)
        self.assertEqual(parsed["continuation"], "DONE")
        self.assertEqual(parsed["profile"], "EFB")

    def test_recovery_safe_wait_recognized(self):
        d = document(profile="Ca/Ca")
        d["safe_wait_next_stage"] = "Main Charge"
        p = validated_session(d, file_mtime_s=9999, observed_at_s=10000)
        self.assertEqual(p["continuation"], "MAIN")

    def test_agm_never_eligible(self):
        self.assertIsNone(validated_session(document(profile="AGM"), file_mtime_s=9999, observed_at_s=10000))

    def test_missing_trace_id_rejected(self):
        d = document()
        d.pop("v2_trace_session_id")
        self.assertIsNone(validated_session(d, file_mtime_s=9999, observed_at_s=10000))

    def test_idle_never_eligible(self):
        self.assertIsNone(validated_session(document(stage="Idle"), file_mtime_s=9999, observed_at_s=10000))

    def test_stale_or_future_session_file_rejected(self):
        d = document()
        self.assertIsNone(validated_session(d, file_mtime_s=9000, observed_at_s=10000))
        self.assertIsNone(validated_session(d, file_mtime_s=10001, observed_at_s=10000))

    def test_bad_epochs_and_destination_rejected(self):
        for start in (None, -1, 0, "broken", True, 11000):
            d = document()
            d["safe_wait_start"] = start
            self.assertIsNone(validated_session(d, file_mtime_s=9999, observed_at_s=10000))
        d = document()
        d["safe_wait_next_stage"] = "Mix Mode"
        self.assertIsNone(validated_session(d, file_mtime_s=9999, observed_at_s=10000))

    def test_missing_corrupt_and_real_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "charge_session.json"
            self.assertIsNone(read_session(p, now_s=10000))
            p.write_text("{bad")
            os.utime(p, (9999, 9999))
            self.assertIsNone(read_session(p, now_s=10000))
            p.write_text(json.dumps(document()))
            os.utime(p, (9999, 9999))
            self.assertEqual(read_session(p, now_s=10000)["profile"], "EFB")


class CollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "charge_session.json"
        self.db = await aiosqlite.connect(":memory:")
        self.collector = PassiveCollector(session_file=self.path)

    async def asyncTearDown(self):
        await self.db.close()

    async def count(self):
        cur = await self.db.execute("SELECT COUNT(*) FROM voltage_relaxation_samples")
        return (await cur.fetchone())[0]

    async def test_no_session_makes_no_ha_calls_or_records(self):
        ha = AsyncMock()
        result = await self.collector.poll(self.db, ha, now_s=10000)
        self.assertEqual(result["status"], "no_eligible_safe_wait")
        ha.get_all_live.assert_not_awaited()
        self.assertEqual(await self.count(), 0)

    async def test_real_session_inserts_sample(self):
        self.path.write_text(json.dumps(document()))
        os.utime(self.path, (9999, 9999))
        ha = AsyncMock()
        ha.get_all_live.return_value = canonical_live()
        result = await self.collector.poll(self.db, ha, now_s=10000)
        self.assertEqual(result["status"], "sample_written")
        self.assertEqual(await self.count(), 1)

    async def test_unknown_output_refuses_sample(self):
        self.path.write_text(json.dumps(document()))
        os.utime(self.path, (9999, 9999))
        ha = AsyncMock()
        ha.get_all_live.return_value = canonical_live(output="unavailable")
        result = await self.collector.poll(self.db, ha, now_s=10000)
        self.assertEqual(result["status"], "no_fresh_off_evidence")
        self.assertEqual(await self.count(), 0)

    async def test_stale_file_after_valid_run_closes_segment(self):
        self.path.write_text(json.dumps(document()))
        os.utime(self.path, (9999, 9999))
        ha = AsyncMock()
        ha.get_all_live.return_value = canonical_live()
        await self.collector.poll(self.db, ha, now_s=10000)
        result = await self.collector.poll(self.db, ha, now_s=10900)
        self.assertEqual(result["status"], "no_eligible_safe_wait")
        cur = await self.db.execute("SELECT status FROM voltage_relaxation_runs")
        self.assertEqual((await cur.fetchone())[0], "closed")


if __name__ == "__main__":
    unittest.main()
