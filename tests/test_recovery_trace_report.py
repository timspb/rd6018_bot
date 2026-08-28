import os
import tempfile
import unittest

import database
from pb_domain import BatteryCondition, ChargeIntent
from recovery_trace_report import build_trace_report
from recovery_trace_store import record_shadow_trace


class RecoveryTraceReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "report.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    async def _record(
        self,
        ts,
        *,
        stage,
        after=None,
        decision="continue",
        disagreement=None,
        first_stage_state=None,
        c_rate=None,
        audit_code=None,
        audit_severity=None,
    ):
        shadow = {
            "status": "ok",
            "decision": decision,
            "reason": "test decision",
            "legacy_effect": "continue",
            "disagreement": disagreement,
            "trace_point": {
                "timestamp_s": ts,
                "stage": stage,
                "legacy_stage_after": after or stage,
                "voltage_v": 14.8 if "Main" in stage else 16.4,
                "current_a": 0.6,
                "temp_c": 25.0,
                "is_cv": True,
                "is_cc": False,
                "target_voltage_v": 14.8 if "Main" in stage else 16.5,
                "ah": 5.0,
                "output_on": True,
            },
        }
        if first_stage_state is not None:
            shadow["first_stage"] = {
                "state": first_stage_state,
                "current_c_rate": c_rate,
            }
        if audit_code is not None:
            shadow["transition_audit"] = {
                "code": audit_code,
                "severity": audit_severity,
                "reason": "legacy escalation audit",
            }
        await record_shadow_trace(
            session_id="calibration-session",
            started_at=100.0,
            battery_id="efb-70",
            battery_type="EFB",
            capacity_ah=70,
            intent=ChargeIntent.RECOVERY,
            condition_before=BatteryCondition.SULFATED_SUSPECTED,
            shadow=shadow,
        )

    async def test_report_counts_main_hv_audit_and_mix_finish_lead(self):
        await self._record(
            100.0,
            stage="Main Charge",
            after="Десульфатация",
            first_stage_state="stuck_plateau",
            c_rate=0.0085,
            audit_code="legacy_hv_escalation_after_stuck_plateau",
            audit_severity="info",
        )
        await self._record(
            200.0,
            stage="Mix Mode",
            decision="finish_stage",
            disagreement="v2_would_finish_stage",
        )
        await self._record(
            500.0,
            stage="Mix Mode",
            after="Безопасное ожидание",
            decision="finish_stage",
        )

        report = await build_trace_report("calibration-session")
        self.assertEqual(report["samples"]["total"], 3)
        self.assertEqual(report["first_stage_states"]["stuck_plateau"], 1)
        self.assertEqual(
            report["transition_audits"]["codes"]["legacy_hv_escalation_after_stuck_plateau"],
            1,
        )
        self.assertEqual(report["disagreements"]["v2_would_finish_stage"], 1)
        self.assertEqual(report["timing"]["first_main_to_hv_at"], 100.0)
        self.assertEqual(report["timing"]["first_v2_finish_stage_at"], 200.0)
        self.assertEqual(report["timing"]["first_legacy_mix_exit_at"], 500.0)
        self.assertEqual(report["timing"]["v2_finish_lead_seconds"], 300.0)

    async def test_review_and_safety_samples_are_kept_for_calibration(self):
        await self._record(
            100.0,
            stage="Main Charge",
            after="Десульфатация",
            first_stage_state="thermally_unstable",
            c_rate=0.009,
            audit_code="legacy_hv_escalation_with_unstable_evidence",
            audit_severity="safety",
        )
        report = await build_trace_report("calibration-session")
        self.assertEqual(report["transition_audits"]["severity"]["safety"], 1)
        self.assertEqual(len(report["calibration_samples"]), 1)
        sample = report["calibration_samples"][0]
        self.assertEqual(sample["first_stage_state"], "thermally_unstable")
        self.assertAlmostEqual(sample["current_c_rate"], 0.009)
        self.assertEqual(sample["transition_audit_severity"], "safety")

    async def test_unknown_session_is_rejected(self):
        with self.assertRaises(KeyError):
            await build_trace_report("missing")


if __name__ == "__main__":
    unittest.main()
