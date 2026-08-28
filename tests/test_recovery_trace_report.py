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
        events=None,
        current_min_a=None,
        reversal_delta_a=None,
    ):
        shadow = {
            "status": "ok",
            "decision": decision,
            "reason": "test decision",
            "legacy_effect": "continue",
            "disagreement": disagreement,
            "events": list(events or []),
            "metrics": {
                "current_min_a": current_min_a,
                "delta_current_from_min_a": reversal_delta_a,
            },
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
            events=["current_reversal_confirmed", "end_of_charge_likely"],
            current_min_a=0.50,
            reversal_delta_a=0.16,
        )
        await self._record(
            300.0,
            stage="Mix Mode",
            after="🌡 Остывание",
            decision="pause_thermal",
        )
        await self._record(
            500.0,
            stage="Mix Mode",
            after="Безопасное ожидание",
            decision="finish_stage",
            current_min_a=0.50,
            reversal_delta_a=0.18,
        )

        report = await build_trace_report("calibration-session")
        self.assertEqual(report["samples"]["total"], 4)
        self.assertEqual(report["first_stage_states"]["stuck_plateau"], 1)
        self.assertEqual(
            report["transition_audits"]["codes"]["legacy_hv_escalation_after_stuck_plateau"],
            1,
        )
        self.assertEqual(report["disagreements"]["v2_would_finish_stage"], 1)
        self.assertEqual(report["timing"]["first_main_to_hv_at"], 100.0)
        self.assertEqual(report["timing"]["first_v2_finish_stage_at"], 200.0)
        self.assertEqual(report["timing"]["first_v2_mix_finish_at"], 200.0)
        self.assertEqual(report["timing"]["first_interrupted_mix_exit_at"], 300.0)
        self.assertEqual(report["timing"]["first_legacy_mix_exit_at"], 500.0)
        self.assertEqual(report["timing"]["v2_finish_lead_seconds"], 300.0)

        exits = report["mix_exits"]
        self.assertEqual(exits["interrupted_count"], 1)
        self.assertEqual(exits["terminal_count"], 1)
        self.assertEqual(exits["first_interrupted_at"], 300.0)
        self.assertEqual(exits["first_terminal_at"], 500.0)
        self.assertEqual(exits["interrupted_transitions"]["Mix Mode -> 🌡 Остывание"], 1)
        self.assertEqual(exits["terminal_transitions"]["Mix Mode -> Безопасное ожидание"], 1)

        reversal = report["hv_reversal"]
        self.assertEqual(reversal["confirmed_count"], 1)
        self.assertEqual(reversal["first_confirmed_at"], 200.0)
        self.assertAlmostEqual(reversal["reversal_delta_a"]["median"], 0.16)
        self.assertAlmostEqual(reversal["reversal_delta_over_imin"]["median"], 0.32)
        self.assertAlmostEqual(reversal["reversal_delta_c_rate"]["median"], 0.16 / 70.0)
        self.assertAlmostEqual(reversal["current_min_c_rate"]["median"], 0.50 / 70.0)
        mix = reversal["by_stage"]["mix mode"]
        self.assertEqual(mix["confirmed_count"], 1)
        self.assertAlmostEqual(mix["reversal_delta_over_imin"]["median"], 0.32)
        first_finish = reversal["first_v2_finish_reversal"]
        self.assertAlmostEqual(first_finish["reversal_delta_over_imin"], 0.32)
        self.assertAlmostEqual(first_finish["reversal_delta_c_rate"], 0.16 / 70.0)
        first_mix_finish = reversal["first_v2_mix_finish_reversal"]
        self.assertAlmostEqual(first_mix_finish["reversal_delta_over_imin"], 0.32)

    async def test_interrupted_mix_exit_without_terminal_exit_has_no_finish_lag(self):
        await self._record(
            100.0,
            stage="Mix Mode",
            decision="finish_stage",
            events=["current_reversal_confirmed", "end_of_charge_likely"],
            current_min_a=0.40,
            reversal_delta_a=0.13,
        )
        await self._record(
            200.0,
            stage="Mix Mode",
            after="🌡 Остывание",
            decision="pause_thermal",
        )

        report = await build_trace_report("calibration-session")
        self.assertEqual(report["mix_exits"]["interrupted_count"], 1)
        self.assertEqual(report["mix_exits"]["terminal_count"], 0)
        self.assertEqual(report["timing"]["first_interrupted_mix_exit_at"], 200.0)
        self.assertIsNone(report["timing"]["first_legacy_mix_exit_at"])
        self.assertIsNone(report["timing"]["v2_finish_lead_seconds"])

    async def test_desulf_finish_does_not_contaminate_mix_finish_lead(self):
        await self._record(
            100.0,
            stage="Десульфатация",
            decision="finish_stage",
            events=["current_reversal_confirmed", "end_of_charge_likely"],
            current_min_a=0.50,
            reversal_delta_a=0.16,
        )
        await self._record(
            250.0,
            stage="Mix Mode",
            decision="finish_stage",
            events=["current_reversal_confirmed", "end_of_charge_likely"],
            current_min_a=0.45,
            reversal_delta_a=0.15,
        )
        await self._record(
            550.0,
            stage="Mix Mode",
            after="Безопасное ожидание",
            decision="finish_stage",
        )

        report = await build_trace_report("calibration-session")
        self.assertEqual(report["timing"]["first_v2_finish_stage_at"], 100.0)
        self.assertEqual(report["timing"]["first_v2_mix_finish_at"], 250.0)
        self.assertEqual(report["timing"]["first_legacy_mix_exit_at"], 550.0)
        self.assertEqual(report["timing"]["v2_finish_lead_seconds"], 300.0)
        self.assertAlmostEqual(
            report["hv_reversal"]["first_v2_finish_reversal"]["reversal_delta_over_imin"],
            0.32,
        )
        self.assertAlmostEqual(
            report["hv_reversal"]["first_v2_mix_finish_reversal"]["reversal_delta_over_imin"],
            0.15 / 0.45,
        )
        by_stage = report["hv_reversal"]["by_stage"]
        self.assertEqual(by_stage["десульфатация"]["confirmed_count"], 1)
        self.assertEqual(by_stage["mix mode"]["confirmed_count"], 1)
        self.assertAlmostEqual(
            by_stage["десульфатация"]["reversal_delta_over_imin"]["median"],
            0.32,
        )
        self.assertAlmostEqual(
            by_stage["mix mode"]["reversal_delta_over_imin"]["median"],
            0.15 / 0.45,
        )

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

    async def test_reversal_metrics_are_empty_without_real_analyzer_values(self):
        await self._record(
            100.0,
            stage="Mix Mode",
            decision="finish_stage",
            events=["current_reversal_confirmed"],
        )
        report = await build_trace_report("calibration-session")
        reversal = report["hv_reversal"]
        self.assertEqual(reversal["confirmed_count"], 1)
        self.assertIsNone(reversal["reversal_delta_over_imin"]["median"])
        self.assertIsNone(reversal["reversal_delta_c_rate"]["median"])
        self.assertIsNone(reversal["by_stage"]["mix mode"]["reversal_delta_over_imin"]["median"])

    async def test_unknown_session_is_rejected(self):
        with self.assertRaises(KeyError):
            await build_trace_report("missing")


if __name__ == "__main__":
    unittest.main()
