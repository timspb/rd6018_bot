"""AUTO stage presentation reuses existing evidence and the caller clock."""
import unittest
from types import SimpleNamespace as NS
from runtime.ui.components.hmi_auto_stage_progress import auto_stage_progress


class AutoStageProjectionTests(unittest.TestCase):
    def test_mix_cv_reuses_accepted_delta_and_source_once(self):
        reads=[]
        snapshot={
            "runtime_evidence_available": True,
            "finish_hold_started_at": None,
            "metrics":{
                "current_min_a":1.85,
                "delta_current_from_min_a":0.04,
                "reversal_threshold_a":0.555,
            },
        }
        def source():
            reads.append(True)
            return snapshot
        controller=NS(ui_support_snapshot=source)
        app=NS(_format_stage_progress_line=lambda _: "source progress")
        progress,status,returned=auto_stage_progress(
            app,controller,{"current":1.89},stage="Mix Mode",regulator="CV",
            telemetry_stale=False,battery_type="EFB",capacity=80,now_s=lambda:10000.,
        )
        self.assertEqual(progress,"source progress")
        self.assertIn("Imin 1.85 A",status)
        self.assertIn("I≥2.405 A",status)
        self.assertIs(returned,snapshot)
        self.assertEqual(len(reads),1)

    def test_mix_cc_invalid_vmax_clock_keeps_delta_evidence_visible(self):
        for invalid_age in (float("nan"), float("inf"), -3.0, "invalid"):
            with self.subTest(age=invalid_age):
                controller=NS(ui_support_snapshot=lambda:{
                    "runtime_evidence_available":True,
                    "metrics":{
                        "voltage_max_v":16.55,
                        "seconds_since_voltage_max":invalid_age,
                        "delta_voltage_from_max_v":0.03,
                        "voltage_reversal_threshold_v":0.10,
                    },
                })
                _,status,_=auto_stage_progress(
                    NS(),controller,{},stage="Mix Mode",regulator="CC",
                    telemetry_stale=False,battery_type="EFB",capacity=80,
                    now_s=lambda:10000.,
                )
                self.assertIn("Vmax 16.55 V",status)
                self.assertIn("U≤16.450 V",status)

    def test_nonmix_cc_future_clock_cannot_invent_elapsed_hold(self):
        controller=NS(ui_support_snapshot=lambda:{
            "runtime_evidence_available":True,
            "finish_hold_started_at":12000.,
            "metrics":{"voltage_max_v":15.5,"seconds_since_voltage_max":float("nan")},
        })
        _,status,_=auto_stage_progress(
            NS(),controller,{},stage="Cooling",regulator="CC",
            telemetry_stale=False,battery_type="EFB",capacity=80,
            now_s=lambda:10000.,
        )
        self.assertIn("время максимума не подтверждено",status)
        self.assertNotIn("⏱ 0ч",status)

    def test_nonmix_cv_invalid_hold_clock_never_blanks_status_or_claims_zero_age(self):
        for invalid_hold in (float("nan"), float("inf"), "bad", 12000.):
            with self.subTest(started=invalid_hold):
                controller=NS(ui_support_snapshot=lambda:{
                    "runtime_evidence_available":True,
                    "finish_hold_started_at":invalid_hold,
                    "metrics":{"current_min_a":0.32,"seconds_since_current_min":float("nan")},
                })
                _,status,_=auto_stage_progress(
                    NS(),controller,{},stage="Cooling",regulator="CV",
                    telemetry_stale=False,battery_type="Ca/Ca",capacity=72,
                    now_s=lambda:10000.,
                )
                self.assertIn("Imin 0.32 A",status)
                self.assertIn("время минимума не подтверждено",status)
                self.assertNotIn("⏱ 0ч",status)

    def test_mix_finish_hold_invalid_current_clock_does_not_blank_panel(self):
        from runtime.ui.components.mix_stage_progress import mix_finish_hold_status
        evidence = {
            "delta_reported": True,
            "finish_evidence": {
                "available": True, "mode": "CV",
                "reference_value": 1.85, "accepted_delta": 0.55,
            },
        }
        for now in (float("nan"), float("inf"), float("-inf"), -1., 0.):
            with self.subTest(now=now):
                status = mix_finish_hold_status(
                    snapshot=evidence, started_at=100.,
                    hold_seconds=7200., now_s=now,
                )
                self.assertIn("время не подтверждено", status)
                self.assertNotIn("до SAFE_WAIT", status)
        valid = mix_finish_hold_status(
            snapshot=evidence, started_at=100., hold_seconds=7200., now_s=160.,
        )
        self.assertIn("ΔI подтверждена", valid)
        self.assertIn("до SAFE_WAIT", valid)

    def test_mix_finish_hold_does_not_confirm_nonpositive_delta_proof(self):
        from runtime.ui.components.mix_stage_progress import mix_finish_hold_status
        for mode, reference in (("CV", 1.85), ("CC", 16.55)):
            for bad_reference, bad_delta in ((reference, 0.0), (reference, -0.10), (0.0, 0.1), (-1.0, 0.1)):
                with self.subTest(mode=mode, reference=bad_reference, delta=bad_delta):
                    snapshot = {"delta_reported": True, "finish_evidence": {
                        "available": True, "mode": mode,
                        "reference_value": bad_reference,
                        "accepted_delta": bad_delta,
                    }}
                    status = mix_finish_hold_status(
                        snapshot=snapshot, started_at=100.0,
                        hold_seconds=7200.0, now_s=160.0,
                    )
                    self.assertIn("Δ evidence недоступно", status)
                    self.assertNotIn("подтверждена", status)
            valid = {"delta_reported": True, "finish_evidence": {
                "available": True, "mode": mode,
                "reference_value": reference, "accepted_delta": 0.10,
            }}
            self.assertIn("подтверждена", mix_finish_hold_status(
                snapshot=valid, started_at=100.0,
                hold_seconds=7200.0, now_s=160.0,
            ))

    def test_stale_telemetry_never_calls_legacy_formatter(self):
        controller=NS(ui_support_snapshot=lambda:{"runtime_evidence_available":False})
        def forbidden(_): raise AssertionError("formatting stale telemetry")
        progress,status,_=auto_stage_progress(
            NS(_format_stage_progress_line=forbidden),controller,{},
            stage="Mix Mode",regulator="",telemetry_stale=True,
            battery_type="EFB",capacity=80,now_s=lambda:10000.,
        )
        self.assertEqual(progress,"")
        self.assertEqual(status,"")

    def test_controller_snapshot_error_remains_nonfatal(self):
        def broken(): raise RuntimeError("offline analyzer")
        progress,status,snapshot=auto_stage_progress(
            NS(),NS(ui_support_snapshot=broken),{},
            stage="Mix Mode",regulator="CV",telemetry_stale=False,
            battery_type="EFB",capacity=80,now_s=lambda:10000.,
        )
        self.assertEqual((progress,status,snapshot),("","",{}))
