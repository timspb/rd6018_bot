import json
import tempfile
import unittest
from pathlib import Path

from bench_capture import build_dynamic_loop_sample, capture_dynamic_loop_phase, source_signature


def live_sample(*, v_ts="2026-08-30T10:00:00+00:00", i_ts="2026-08-30T10:00:01+00:00", current=5.0):
    return {
        "battery_voltage": 14.102,
        "current": current,
        "set_current": 6.0,
        "voltage": 14.121,
        "temp_ext": 25.0,
        "regulation_code": 1,
        "model_number": 60185,
        "serial_number": 12345678,
        "firmware_version": 131,
        "cal_vout_zero": 1,
        "cal_vout_scale": 2,
        "cal_vbat_zero": 3,
        "cal_vbat_scale": 4,
        "cal_iout_zero": 5,
        "cal_iout_scale": 6,
        "cal_ibat_zero": 7,
        "cal_ibat_scale": 8,
        "_meta": {
            "battery_voltage": {"status": "ok", "last_updated": v_ts},
            "current": {"status": "ok", "last_updated": i_ts},
        },
    }


class FakeReadOnlyClient:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0

    async def get_all_live(self):
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


class BenchCaptureTests(unittest.IsolatedAsyncioTestCase):
    def test_sample_uses_real_ha_source_time_and_preserves_skew(self):
        sample = build_dynamic_loop_sample(
            live_sample(),
            phase="baseline",
            connection_id="clips-a",
            fetched_at_s=123.0,
        )
        self.assertEqual(sample["phase"], "baseline")
        self.assertEqual(sample["connection_id"], "clips-a")
        self.assertEqual(sample["timestamp_s"], 1788084001.0)
        self.assertEqual(sample["source_skew_s"], 1.0)
        self.assertEqual(sample["capture_fetched_at_s"], 123.0)
        self.assertEqual(sample["regulation_mode"], "cc")
        self.assertEqual(sample["calibration_fingerprint"][-8:], [1, 2, 3, 4, 5, 6, 7, 8])

    def test_missing_source_timestamp_is_rejected_instead_of_invented(self):
        live = live_sample()
        live["_meta"]["current"]["last_updated"] = None
        with self.assertRaisesRegex(ValueError, "source timestamp"):
            build_dynamic_loop_sample(live, phase="baseline", connection_id="clips-a")
        self.assertIsNone(source_signature(live))

    async def test_capture_deduplicates_polls_and_only_reads_live_state(self):
        first = live_sample()
        second = live_sample()
        third = live_sample(
            v_ts="2026-08-30T10:00:05+00:00",
            i_ts="2026-08-30T10:00:06+00:00",
            current=4.0,
        )
        client = FakeReadOnlyClient([first, second, third])

        async def no_sleep(_delay):
            return None

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "probe.jsonl"
            summary = await capture_dynamic_loop_phase(
                client,
                path,
                phase="stepped",
                connection_id="clips-a",
                duration_s=60.0,
                poll_interval_s=0.0,
                max_samples=2,
                sleep=no_sleep,
            )
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(summary.written, 2)
        self.assertEqual(summary.duplicate_polls, 1)
        self.assertEqual(summary.invalid_polls, 0)
        self.assertEqual(client.calls, 3)
        self.assertEqual([row["current_a"] for row in rows], [5.0, 4.0])


if __name__ == "__main__":
    unittest.main()
