import asyncio
import json
import math
import unittest

import aiosqlite

from runtime.charge.controller_state import STAGE_SAFE_WAIT
from runtime.charge.observability.voltage_relaxation import (
    VoltageRelaxationRecorder, calculate_signature, qualify,
)


def sample(v=13.2, *, output="off", current=0.0, age=2.0, temp=22.0):
    return {
        "battery_voltage": v, "voltage": 0, "switch": output, "current": current,
        "temp_ext": temp, "_meta": {
            k: {"status": "ok", "age_s": age}
            for k in ("battery_voltage", "switch", "current")
        },
    }


def context(*, live=None, stage=STAGE_SAFE_WAIT, profile="EFB",
            session="s1", epoch=990, next_stage="DONE", now=1000):
    return dict(live=sample() if live is None else live, stage=stage,
                safe_wait_stage=STAGE_SAFE_WAIT, session_id=session, battery_id="test-battery",
                profile=profile, safe_wait_epoch_s=epoch,
                continuation=next_stage, observed_at_s=now)


class QualificationTests(unittest.TestCase):
    def test_efb_actual_canonical_stage(self):
        self.assertEqual(qualify(**context()).profile, "EFB")

    def test_calcium_actual_canonical_stage(self):
        self.assertEqual(qualify(**context(profile="Ca/Ca")).profile, "CA/CA")

    def test_no_agm_recording(self):
        self.assertIsNone(qualify(**context(profile="AGM")))

    def test_battery_identity_partitions_repeated_session(self):
        first = qualify(**context())
        other = context()
        other["battery_id"] = "other-battery"
        self.assertNotEqual(first.run_key, qualify(**other).run_key)

    def test_no_mix_recording(self):
        self.assertIsNone(qualify(**context(stage="Mix Mode")))

    def test_output_on_unknown_rejected(self):
        for output in ("on", "unavailable", None, "1"):
            with self.subTest(output=output):
                self.assertIsNone(qualify(**context(live=sample(output=output))))

    def test_inconsistent_off_current_rejected(self):
        self.assertIsNone(qualify(**context(live=sample(current=0.1))))

    def test_missing_stale_or_invalid_voltage_rejected(self):
        for voltage in (None, "unavailable", 0, float("nan"), -5, 31):
            with self.subTest(voltage=voltage):
                self.assertIsNone(qualify(**context(live=sample(v=voltage))))
        self.assertIsNone(qualify(**context(live=sample(age=9999))))
        bad = sample()
        bad["_meta"]["battery_voltage"]["status"] = "unavailable"
        self.assertIsNone(qualify(**context(live=bad)))

    def test_output_voltage_zero_does_not_replace_battery_voltage(self):
        valid = qualify(**context(live=sample(v=13.21)))
        self.assertEqual(valid.voltage_v, 13.21)

    def test_missing_session_epoch_and_next_rejected(self):
        self.assertIsNone(qualify(**context(session=None)))
        self.assertIsNone(qualify(**context(epoch=0)))
        self.assertIsNone(qualify(**context(next_stage="Storage")))
        self.assertIsNone(qualify(**context(now=100, epoch=101)))

    def test_canonical_live_v2_output_heartbeat_metadata(self):
        from rd6018_telemetry import canonicalize_live
        original = sample(v=13.28)
        original.pop("switch")
        original["output_state_code_v2"] = 0
        original["_meta"].pop("switch")
        original["_meta"]["output_state_code_v2"] = {"status": "ok", "age_s": 1.0}
        live = canonicalize_live(original)
        self.assertEqual(live["switch"], "off")
        self.assertEqual(live["_meta"]["switch"]["source_key"], "output_state_code_v2")
        self.assertEqual(qualify(**context(live=live)).voltage_v, 13.28)

    def test_missing_temperature_kept_as_no_temperature(self):
        valid = qualify(**context(live=sample(temp=None)))
        self.assertIsNone(valid.temp_c)

    def test_run_key_bound_to_session_epoch_and_destination(self):
        base = qualify(**context())
        for kw in ({"session": "s2"}, {"epoch": 991}, {"next_stage": "MAIN"}):
            self.assertNotEqual(base.run_key, qualify(**context(**kw)).run_key)


class WindowTests(unittest.TestCase):
    def test_expected_linear_voltage_slope(self):
        points = [(1000+t, 13.5 - 0.001*(t/60)) for t in range(0, 3601, 60)]
        report = calculate_signature(points)
        self.assertEqual(report["relax_5_15"]["status"], "measured")
        self.assertAlmostEqual(report["relax_5_15"]["slope_mv_per_min"], -1, places=3)
        self.assertAlmostEqual(report["relax_15_60"]["estimated_drop_mv"], 45, places=2)
        self.assertAlmostEqual(report["slope_magnitude_ratio"], 1, places=3)

    def test_early_return_does_not_invent_60m_window(self):
        points = [(1000+t, 13.2 - .002*(t/60)) for t in range(0, 901, 60)]
        report = calculate_signature(points)
        self.assertEqual(report["relax_5_15"]["status"], "measured")
        self.assertEqual(report["relax_15_60"]["status"], "insufficient_data")

    def test_missing_endpoint_returns_insufficient(self):
        points = [(1000+t, 13.5 - 0.001*(t/60)) for t in range(0, 2901, 60)]
        self.assertEqual(calculate_signature(points)["relax_15_60"]["status"], "insufficient_data")

    def test_gap_does_not_interpolate(self):
        times = list(range(0, 501, 60)) + list(range(800, 1801, 60))
        points = [(1000+t, 13.5 - 0.001*(t/60)) for t in times]
        self.assertEqual(calculate_signature(points)["relax_5_15"]["status"], "insufficient_data")

    def test_positive_slope_is_recorded_not_reinterpreted(self):
        points = [(1000+t, 13.1 + .001*(t/60)) for t in range(0, 3601, 60)]
        report = calculate_signature(points)
        self.assertGreater(report["relax_5_15"]["slope_mv_per_min"], 0)
        self.assertEqual(report["interpretation"], "observational_only_not_stratification_proof")


class RecorderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        self.recorder = VoltageRelaxationRecorder()

    async def asyncTearDown(self):
        await self.db.close()

    async def observe(self, **kw):
        return await self.recorder.observe(self.db, **context(**kw))

    async def count(self):
        q = await self.db.execute("SELECT COUNT(*) FROM voltage_relaxation_samples")
        return (await q.fetchone())[0]

    async def runs(self):
        q = await self.db.execute(
            "SELECT segment,status,signature_json,run_key FROM voltage_relaxation_runs ORDER BY segment"
        )
        return await q.fetchall()

    async def test_first_valid_off_creates_durable_run(self):
        result = await self.observe()
        self.assertEqual(result["samples"], 1)
        self.assertEqual(result["elapsed_s"], 0)
        self.assertEqual(await self.count(), 1)

    async def test_declining_voltage_recorded_with_metrics(self):
        for t in range(0, 3601, 60):
            result = await self.observe(now=1000+t, live=sample(v=13.5-.001*t/60))
        self.assertEqual(result["samples"], 61)
        self.assertEqual(result["signature"]["relax_5_15"]["status"], "measured")
        self.assertEqual(result["signature"]["relax_15_60"]["status"], "measured")
        persisted = json.loads((await self.runs())[0][2])
        self.assertEqual(persisted["relax_15_60"]["status"], "measured")

    async def test_stops_at_stage_change_without_waiting_60m(self):
        await self.observe()
        await self.observe(now=1060)
        await self.observe(now=1090, stage="Done")
        self.assertEqual((await self.runs())[0][1], "closed")
        self.assertEqual(await self.count(), 2)

    async def test_output_on_breaks_off_segment(self):
        await self.observe()
        await self.observe(now=1030, live=sample(output="on"))
        await self.observe(now=1060)
        self.assertEqual(len(await self.runs()), 2)
        self.assertEqual((await self.runs())[0][1], "closed")

    async def test_stale_telemetry_closes_segment(self):
        await self.observe()
        await self.observe(now=1030, live=sample(age=999))
        await self.observe(now=1060)
        self.assertEqual(len(await self.runs()), 2)

    async def test_long_gap_does_not_fabricate_continuity(self):
        await self.observe()
        result = await self.observe(now=2000)
        self.assertEqual(result["elapsed_s"], 0)
        self.assertEqual(result["segment"], 2)

    async def test_different_session_never_joins_previous_data(self):
        a = await self.observe()
        b = await self.observe(now=1030, session="s2")
        self.assertNotEqual(a["run_key"], b["run_key"])
        self.assertEqual((await self.runs())[0][1], "closed")

    async def test_restart_recovers_recent_off_segment(self):
        await self.observe()
        restarted = VoltageRelaxationRecorder()
        second = await restarted.observe(self.db, **context(now=1060))
        self.assertEqual(second["segment"], 1)
        self.assertEqual(second["samples"], 2)

    async def test_restart_after_gap_closes_and_forks(self):
        await self.observe()
        restarted = VoltageRelaxationRecorder()
        second = await restarted.observe(self.db, **context(now=1600))
        self.assertEqual(second["segment"], 2)
        self.assertEqual(second["elapsed_s"], 0)

    async def test_duplicate_or_too_fast_sample_not_written(self):
        await self.observe()
        self.assertIsNone(await self.observe(now=1001))
        self.assertIsNone(await self.observe(now=1000))
        self.assertEqual(await self.count(), 1)

    async def test_agm_never_creates_a_row(self):
        await self.observe(profile="AGM")
        self.assertEqual(await self.count(), 0)

    async def test_no_action_or_hardware_methods_exposed(self):
        import inspect
        source = inspect.getsource(VoltageRelaxationRecorder)
        for forbidden in ("turn_on(", "enable_output(", "set_current(", "set_voltage("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
