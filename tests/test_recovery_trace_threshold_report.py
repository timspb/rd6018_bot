import os
import tempfile
import unittest

import database
from pb_domain import BatteryCondition, ChargeIntent
from recovery_trace_report import build_trace_report
from recovery_trace_store import record_shadow_trace


class RecoveryTraceThresholdReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "threshold-report.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def test_report_exposes_frozen_relative_threshold(self):
        shadow = {
            "status": "ok",
            "decision": "finish_stage",
            "reason": "confirmed_current_reversal_after_imin_with_stable_u_t",
            "legacy_effect": "continue",
            "disagreement": "v2_would_finish_stage",
            "events": ["current_reversal_confirmed", "end_of_charge_likely"],
            "metrics": {
                "current_min_a": 0.50,
                "delta_current_from_min_a": 0.16,
            },
            "trace_point": {
                "timestamp_s": 100.0,
                "stage": "Mix Mode",
                "legacy_stage_after": "Mix Mode",
                "voltage_v": 16.5,
                "current_a": 0.66,
                "temp_c": 25.0,
                "is_cv": True,
                "is_cc": False,
                "target_voltage_v": 16.5,
                "ah": 8.0,
                "output_on": True,
            },
        }
        await record_shadow_trace(
            session_id="threshold-session",
            started_at=10.0,
            battery_id="efb-70",
            battery_type="EFB",
            capacity_ah=70,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.SULFATED_SUSPECTED,
            shadow=shadow,
        )

        report = await build_trace_report("threshold-session")
        config = report["signal_config"]
        self.assertFalse(config["changed_within_session"])
        self.assertAlmostEqual(config["captured"]["reversal_ratio"], 0.30)
        self.assertAlmostEqual(config["captured"]["reversal_abs_floor_a"], 0.03)

        reversal = report["hv_reversal"]
        self.assertAlmostEqual(reversal["reversal_threshold_a"]["median"], 0.15)
        self.assertAlmostEqual(reversal["reversal_threshold_over_imin"]["median"], 0.30)
        self.assertAlmostEqual(reversal["reversal_threshold_c_rate"]["median"], 0.15 / 70.0)
        self.assertEqual(reversal["threshold_source"]["relative_to_imin"], 1)
        mix = reversal["by_stage"]["mix mode"]
        self.assertAlmostEqual(mix["reversal_threshold_over_imin"]["median"], 0.30)
        self.assertEqual(mix["threshold_source"]["relative_to_imin"], 1)


if __name__ == "__main__":
    unittest.main()
