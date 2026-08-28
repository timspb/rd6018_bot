import os
import tempfile
import unittest

import database
from pb_domain import BatteryCondition, ChargeIntent
from recovery_trace_report import build_trace_report
from recovery_trace_store import export_replay_document, record_shadow_trace


class CCVoltageTraceReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "cc-report.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def _record(self, ts: float, *, reversal: bool = False) -> None:
        shadow = {
            "status": "ok",
            "decision": "finish_stage" if reversal else "continue",
            "reason": "confirmed_cc_voltage_reversal_after_vmax_with_stable_t" if reversal else "test",
            "events": ["voltage_reversal_confirmed", "end_of_charge_likely"] if reversal else [],
            "metrics": {
                "voltage_max_v": 16.35 if reversal else 16.35,
                "seconds_since_voltage_max": 600.0 if reversal else 0.0,
                "delta_voltage_from_max_v": 0.05 if reversal else 0.0,
                "voltage_reversal_threshold_v": 0.03,
                "voltage_reversal_confirmations": 3 if reversal else 0,
            },
            "trace_point": {
                "timestamp_s": ts,
                "stage": "Mix Mode",
                "legacy_stage_after": "Mix Mode",
                "voltage_v": 16.30 if reversal else 16.35,
                "current_a": 1.50,
                "temp_c": 25.0,
                "is_cv": False,
                "is_cc": True,
                "target_voltage_v": 16.50,
                "ah": 10.0,
                "output_on": True,
            },
        }
        await record_shadow_trace(
            session_id="cc-mix",
            started_at=100.0,
            battery_id="cc-battery",
            battery_type="EFB",
            capacity_ah=70,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.SULFATED_SUSPECTED,
            shadow=shadow,
        )

    async def test_cc_voltage_reversal_drives_mix_budget_and_own_distribution(self):
        await self._record(100.0)
        reversal_at = 100.0 + 19.0 * 3600.0
        await self._record(reversal_at, reversal=True)

        report = await build_trace_report("cc-mix")
        cc = report["cc_voltage_reversal"]
        self.assertEqual(cc["confirmed_count"], 1)
        self.assertAlmostEqual(cc["reversal_delta_v"]["median"], 0.05)
        self.assertAlmostEqual(cc["reversal_threshold_v"]["median"], 0.03)
        self.assertEqual(report["mix_time_budget"]["first_mix_reversal_at"], reversal_at)
        self.assertEqual(report["mix_time_budget"]["profile_limit_hours"], 20.0)

    async def test_export_preserves_explicit_cc_mode(self):
        await self._record(100.0)
        exported = await export_replay_document("cc-mix")
        point = exported["cycles"][0]["trace"][0]
        self.assertFalse(point["is_cv"])
        self.assertTrue(point["is_cc"])


if __name__ == "__main__":
    unittest.main()
