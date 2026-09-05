import os
import tempfile
import unittest

import database
from pb_domain import BatteryCondition, ChargeIntent
from recovery_trace_report import build_trace_report
from recovery_trace_store import record_shadow_trace


class MixDeltaTimeBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "budget.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def _record(self, ts: float, *, reversal: bool = False) -> None:
        shadow = {
            "status": "ok",
            "decision": "finish_stage" if reversal else "continue",
            "reason": "test",
            "events": ["current_reversal_confirmed", "end_of_charge_likely"] if reversal else [],
            "metrics": {
                "current_min_a": 0.50 if reversal else None,
                "delta_current_from_min_a": 0.16 if reversal else None,
                "reversal_threshold_a": 0.15 if reversal else None,
                "reversal_threshold_source": "relative_to_imin" if reversal else None,
            },
            "trace_point": {
                "timestamp_s": ts,
                "stage": "Mix Mode",
                "legacy_stage_after": "Mix Mode",
                "voltage_v": 16.5,
                "current_a": 0.66 if reversal else 0.50,
                "temp_c": 25.0,
                "is_cv": True,
                "is_cc": False,
                "target_voltage_v": 16.5,
                "ah": 10.0,
                "output_on": True,
            },
        }
        await record_shadow_trace(
            session_id="late-efb-mix",
            started_at=100.0,
            battery_id="efb-problem",
            battery_type="EFB",
            capacity_ah=70,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.SULFATED_SUSPECTED,
            shadow=shadow,
        )

    async def test_late_reversal_exposes_required_finish_grace(self):
        mix_start = 100.0
        await self._record(mix_start)
        # Reversal appears 19.5h into an EFB Mix with a nominal 20h window.
        reversal_at = mix_start + 19.5 * 3600.0
        await self._record(reversal_at, reversal=True)

        report = await build_trace_report("late-efb-mix")
        budget = report["mix_time_budget"]

        self.assertEqual(budget["profile_limit_hours"], 20.0)
        self.assertEqual(budget["finish_hold_seconds"], 2 * 3600)
        self.assertAlmostEqual(budget["seconds_remaining_at_reversal"], 30 * 60)
        self.assertFalse(budget["hold_fits_before_nominal_deadline"])
        self.assertAlmostEqual(budget["required_grace_seconds"], 90 * 60)
        self.assertFalse(budget["reversal_after_nominal_deadline"])

    async def test_early_reversal_needs_no_grace(self):
        mix_start = 100.0
        await self._record(mix_start)
        reversal_at = mix_start + 16.0 * 3600.0
        await self._record(reversal_at, reversal=True)

        report = await build_trace_report("late-efb-mix")
        budget = report["mix_time_budget"]

        self.assertTrue(budget["hold_fits_before_nominal_deadline"])
        self.assertEqual(budget["required_grace_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()
