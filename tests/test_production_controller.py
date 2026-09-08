import asyncio
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from first_stage_evidence import FirstStageState
from pb_domain import BatteryCondition, ChargeIntent
from production_controller import ProductionChargeControllerV2
from recovery_session import RecoveryTracePoint


class DummyHass:
    pass


class ProductionControllerTests(unittest.TestCase):
    def _controller(self, profile: str, intent: ChargeIntent, capacity: int = 100):
        controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.configure_recovery_context(
            battery_id="fixture", intent=intent, condition_before=BatteryCondition.UNKNOWN,
        )
        controller.start(profile, capacity)
        return controller

    @staticmethod
    def _flat_record():
        return SimpleNamespace(analysis=SimpleNamespace(metrics=SimpleNamespace(
            d_temp_c_per_min=0.0, d_current_a_per_min=0.0, d_voltage_v_per_min=0.0,
        )))

    def _assess_tail(self, controller, *, timestamp_s, current_a=0.09, voltage_v=14.70, is_cv=True):
        return controller._assess_main_sample(
            stage_before=controller.STAGE_MAIN, target_before=14.70, plateau_since=None,
            timestamp_s=timestamp_s, voltage=voltage_v, current=current_a, is_cv=is_cv,
            record=self._flat_record(),
        )

    def test_normal_agm_cold_main_keeps_temperature_compensation_inside_full_auto_envelope(self):
        controller = self._controller("AGM", ChargeIntent.NORMAL)
        controller.current_stage = controller.STAGE_MAIN
        controller._agm_stage_idx = 3
        voltage_v, current_a = controller._main_target(0.0)
        self.assertAlmostEqual(voltage_v, 15.4)
        self.assertLessEqual(current_a, 10.0)

    def test_recovery_agm_cold_mix_never_exceeds_recovery_ceiling(self):
        controller = self._controller("AGM", ChargeIntent.RECOVERY)
        controller.current_stage = controller.STAGE_MIX
        voltage_v, current_a = controller._mix_target(0.0)
        self.assertAlmostEqual(voltage_v, 16.3)
        self.assertLessEqual(current_a, 3.0)

    def test_normal_intent_allows_standard_mix_target(self):
        controller = self._controller("EFB", ChargeIntent.NORMAL)
        controller.current_stage = controller.STAGE_MIX
        voltage_v, _ = controller._mix_target(25.0)
        self.assertAlmostEqual(voltage_v, 16.5)

    def test_diagnostic_intent_clamps_mix_target_to_main_envelope(self):
        controller = self._controller("EFB", ChargeIntent.DIAGNOSTIC)
        controller.current_stage = controller.STAGE_MIX
        voltage_v, _ = controller._mix_target(25.0)
        self.assertAlmostEqual(voltage_v, 14.8)

    def test_recovery_efb_temperature_compensation_is_bounded_at_16_5(self):
        controller = self._controller("EFB", ChargeIntent.RECOVERY)
        controller.current_stage = controller.STAGE_MIX
        voltage_v, current_a = controller._mix_target(0.0)
        self.assertAlmostEqual(voltage_v, 16.5)
        self.assertLessEqual(current_a, 5.0)

    def test_old_imin_age_cannot_replace_continuous_tail_hold(self):
        controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = 1000.0
        assessment = self._assess_tail(controller, timestamp_s=20_000.0)
        self.assertEqual(assessment.state, FirstStageState.BULK_OR_TAPER)
        self.assertIn("continuous tail hold", assessment.reason)
        self.assertAlmostEqual(controller._v2_continuous_tail_since, 20_000.0)

    def test_caca_tail_becomes_authoritative_only_after_three_continuous_hours(self):
        controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = 1000.0
        start = 20_000.0
        first = self._assess_tail(controller, timestamp_s=start)
        almost = self._assess_tail(controller, timestamp_s=start + 3 * 3600 - 1)
        ready = self._assess_tail(controller, timestamp_s=start + 3 * 3600)
        self.assertEqual(first.state, FirstStageState.BULK_OR_TAPER)
        self.assertEqual(almost.state, FirstStageState.BULK_OR_TAPER)
        self.assertEqual(ready.state, FirstStageState.TAIL_READY)

    def test_excursion_above_tail_resets_continuous_hold(self):
        controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = 1000.0
        start = 20_000.0
        self._assess_tail(controller, timestamp_s=start)
        self._assess_tail(controller, timestamp_s=start + 2 * 3600)
        excursion = self._assess_tail(controller, timestamp_s=start + 2 * 3600 + 60, current_a=0.50)
        returned = self._assess_tail(controller, timestamp_s=start + 3 * 3600 + 60)
        self.assertNotEqual(excursion.state, FirstStageState.TAIL_READY)
        self.assertEqual(returned.state, FirstStageState.BULK_OR_TAPER)
        self.assertAlmostEqual(controller._v2_continuous_tail_since, start + 3 * 3600 + 60)

    def test_stage_restart_resets_continuous_tail_hold(self):
        controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
        controller.current_stage = controller.STAGE_MAIN
        controller.stage_start_time = 1000.0
        start = 20_000.0
        self._assess_tail(controller, timestamp_s=start)
        self._assess_tail(controller, timestamp_s=start + 2 * 3600)
        controller.stage_start_time = start + 2 * 3600 + 30
        after_restart = self._assess_tail(controller, timestamp_s=start + 3 * 3600)
        self.assertEqual(after_restart.state, FirstStageState.BULK_OR_TAPER)
        self.assertAlmostEqual(controller._v2_continuous_tail_since, start + 3 * 3600)

    @staticmethod
    def _legacy_session(*, intent=None):
        document = {
            "profile": "EFB", "stage": "Mix Mode", "stage_start_time": 900.0,
            "target_finish_time": None, "finish_timer_start": None, "ah_limit": 100,
            "start_ah": 0.0, "stage_start_ah": 0.0, "stage_start_voltage": 14.8,
            "stage_start_current": 3.0, "stage_start_temp": 25.0, "current_retries": 0,
            "target_voltage": 16.6, "target_current": 3.0, "agm_stage_idx": 0,
            "safe_wait_next_stage": None, "safe_wait_target_v": 0.0,
            "safe_wait_target_i": 0.0, "safe_wait_start": 0.0, "total_start_time": 800.0,
            "first_stage_hold_since": None, "first_stage_hold_current": None,
            "stuck_current_since": None, "stuck_current_value": None,
            "previous_stage": "Main Charge", "last_transition_reason": "legacy fixture",
            "stage_history": [], "saved_at": 1000.0,
        }
        if intent is not None:
            document.update({
                "v2_trace_session_id": "abc123", "v2_trace_started_at": 800.0,
                "v2_battery_id": "saved-efb", "v2_intent": intent.value,
                "v2_condition_before": BatteryCondition.UNKNOWN.value, "v2_authoritative": True,
            })
        return document

    def _restore_document(self, document):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            with open(session_file, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
            controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("charge_logic.time.time", return_value=1100.0), patch(
                "charge_controller_v2.time.time", return_value=1100.0
            ):
                ok, _ = controller.try_restore_session(16.0, 2.0, 1.0)
                target = controller._get_target_v_i(25.0)
                context = controller.recovery_trace_context
                with open(session_file, "r", encoding="utf-8") as handle:
                    persisted = json.load(handle)
            return ok, target, context, persisted

    def test_pre_v2_restore_defaults_to_normal_and_preserves_standard_mix_envelope(self):
        ok, target, context, persisted = self._restore_document(self._legacy_session())
        self.assertTrue(ok)
        self.assertEqual(context["intent"], ChargeIntent.NORMAL)
        self.assertAlmostEqual(target[0], 16.5)
        self.assertEqual(persisted["v2_intent"], ChargeIntent.NORMAL.value)

    def test_v2_recovery_restore_preserves_recovery_intent_and_ceiling(self):
        ok, target, context, _ = self._restore_document(self._legacy_session(intent=ChargeIntent.RECOVERY))
        self.assertTrue(ok)
        self.assertEqual(context["intent"], ChargeIntent.RECOVERY)
        self.assertAlmostEqual(target[0], 16.5)

    def _runtime_signal_document(
        self, *, output_on=True, observed_at=1000.0, mode="CV", confirmations=0
    ):
        controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 900.0
        controller._v2_target_voltage_v = 16.46
        controller._device_set_voltage = 16.46
        controller._device_set_current = 2.16
        controller._v2_session_signal_context = {
            "stage": controller.STAGE_MIX,
            "mode": mode,
            "session_id": controller._v2_trace_session_id,
            "session_generation": controller._v2_trace_started_at,
            "output_on": output_on,
            "cv_state": mode == "CV",
            "cc_state": mode == "CC",
            "telemetry_valid": True,
            "telemetry_observed_at": observed_at,
            "telemetry_age_s": 0.0,
            "target_voltage_v": 16.46,
            "current_min_a": 0.66 if mode == "CV" else None,
            "current_min_time_s": 0.0 if mode == "CV" else None,
            "delta_reference_a": 0.66 if mode == "CV" else None,
            "voltage_max_v": 16.47 if mode == "CC" else None,
            "voltage_max_time_s": 0.0 if mode == "CC" else None,
            "delta_reference_v": 16.47 if mode == "CC" else None,
            "reversal_threshold_a": 0.198,
            "reversal_confirmations": confirmations,
            "last_reversal_confirmation_s": observed_at - 50.0 if confirmations else None,
            "reversal_emitted": False,
            "voltage_reversal_confirmations": confirmations if mode == "CC" else 0,
            "voltage_last_reversal_confirmation_s": (
                observed_at - 50.0 if mode == "CC" and confirmations else None
            ),
            "voltage_reversal_emitted": False,
        }
        return controller

    def _persist_runtime_signal(self, controller, session_file):
        with patch("charge_logic.SESSION_FILE", session_file), patch(
            "charge_controller_v2.SESSION_FILE", session_file
        ), patch("production_controller.SESSION_FILE", session_file), patch(
            "charge_logic.time.time", return_value=1000.0
        ), patch("charge_controller_v2.time.time", return_value=1000.0), patch(
            "production_controller.time.time", return_value=1000.0
        ):
            controller._save_session(16.47, 0.66, 1.0)

    def _persist_finish_state(self, session_file, mode="CV"):
        controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 800.0
        controller.finish_timer_start = 900.0
        controller._delta_reported = True
        controller._delta_trigger_mode = mode
        controller._finish_evidence = {
            "version": 1,
            "mode": mode,
            "reference_value": 0.66 if mode == "CV" else 16.47,
            "accepted_delta": 0.24 if mode == "CV" else 0.05,
            "accepted_at": 900.0,
            "session_id": controller._v2_trace_session_id,
        }
        with patch("charge_logic.SESSION_FILE", session_file), patch(
            "charge_controller_v2.SESSION_FILE", session_file
        ), patch("production_controller.SESSION_FILE", session_file), patch(
            "charge_logic.time.time", return_value=1000.0
        ), patch("charge_controller_v2.time.time", return_value=1000.0), patch(
            "production_controller.time.time", return_value=1000.0
        ):
            controller._save_session(16.47, 0.66, 1.0)

    def test_mix_runtime_signal_survives_restore_and_delta_continues(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            original = self._runtime_signal_document(confirmations=2)
            self._persist_runtime_signal(original, session_file)
            with open(session_file, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertAlmostEqual(saved["runtime_signal"]["current_min_a"], 0.66)

            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1010.0
            ), patch("charge_controller_v2.time.time", return_value=1010.0), patch(
                "production_controller.time.time", return_value=1010.0
            ):
                ok, _ = restored.try_restore_session(
                    16.47, 0.66, 1.0, output_is_on=True, is_cv=True, is_cc=False
                )

            self.assertTrue(ok)
            analyzer = restored._v2_runtime.tracker._analyzer
            self.assertAlmostEqual(analyzer._current_min_a, 0.66)
            self.assertEqual(analyzer._reversal_confirmations, 2)
            analysis = restored._v2_runtime.tracker.observe(
                RecoveryTracePoint(
                    timestamp_s=1200.0,
                    stage=restored.STAGE_MIX,
                    voltage_v=16.47,
                    current_a=0.90,
                    temp_c=27.0,
                    is_cv=True,
                    is_cc=False,
                    target_voltage_v=16.46,
                    ah=2.0,
                )
            )
            self.assertAlmostEqual(analysis.metrics.current_min_a, 0.66)
            self.assertAlmostEqual(analysis.metrics.delta_current_from_min_a, 0.24)

    def test_cc_runtime_signal_survives_restore_and_delta_continues(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            original = self._runtime_signal_document(mode="CC", confirmations=2)
            self._persist_runtime_signal(original, session_file)
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1010.0
            ), patch("charge_controller_v2.time.time", return_value=1010.0), patch(
                "production_controller.time.time", return_value=1010.0
            ):
                ok, _ = restored.try_restore_session(
                    16.47, 0.66, 1.0, output_is_on=True, is_cv=False, is_cc=True
                )
            self.assertTrue(ok)
            analyzer = restored._v2_runtime.tracker._analyzer
            self.assertAlmostEqual(analyzer._voltage_max_v, 16.47)
            self.assertEqual(analyzer._voltage_reversal_confirmations, 2)
            analysis = restored._v2_runtime.tracker.observe(
                RecoveryTracePoint(
                    timestamp_s=1200.0,
                    stage=restored.STAGE_MIX,
                    voltage_v=16.40,
                    current_a=0.66,
                    temp_c=27.0,
                    is_cv=False,
                    is_cc=True,
                    target_voltage_v=16.46,
                    ah=2.0,
                )
            )
            self.assertAlmostEqual(analysis.metrics.voltage_max_v, 16.47)
            self.assertAlmostEqual(analysis.metrics.delta_voltage_from_max_v, 0.07)

    def test_cc_runtime_signal_uses_real_voltage_reversal_state_for_restore(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
            controller.current_stage = controller.STAGE_MIX
            controller.stage_start_time = time.time() - 240.0
            controller._v2_target_voltage_v = 16.46

            async def no_legacy_scaffold(*args, **kwargs):
                return {}

            now = time.time()
            samples = (
                (now - 180.0, 16.30),
                (now - 120.0, 16.30),
                (now - 60.0, 16.26),
                (now, 16.25),
            )
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch.object(
                controller, "_run_legacy_scaffold_tick", new=no_legacy_scaffold
            ):
                for timestamp_s, voltage_v in samples:
                    controller.last_update_time = timestamp_s
                    asyncio.run(
                        controller.tick(
                            voltage_v,
                            1.5,
                            27.0,
                            is_cv=False,
                            ah=1.0,
                            output_is_on=True,
                            is_cc=True,
                        )
                    )

                analyzer = controller._v2_runtime.tracker._analyzer
                self.assertAlmostEqual(analyzer._voltage_max_v, 16.30)
                self.assertEqual(analyzer._voltage_reversal_confirmations, 2)
                self.assertAlmostEqual(analyzer._last_voltage_reversal_confirmation_s, now)
                self.assertFalse(analyzer._voltage_reversal_emitted)

                with open(session_file, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                signal = saved["runtime_signal"]
                self.assertEqual(signal["voltage_reversal_confirmations"], 2)
                self.assertAlmostEqual(
                    signal["voltage_last_reversal_confirmation_s"], now, delta=0.01
                )
                self.assertFalse(signal["voltage_reversal_emitted"])

                restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
                ok, _ = restored.try_restore_session(
                    16.25,
                    1.5,
                    1.0,
                    output_is_on=True,
                    is_cv=False,
                    is_cc=True,
                )

            self.assertTrue(ok)
            restored_analyzer = restored._v2_runtime.tracker._analyzer
            self.assertAlmostEqual(restored_analyzer._voltage_max_v, 16.30)
            self.assertAlmostEqual(restored_analyzer._voltage_max_time_s, now - 180.0, delta=0.01)
            self.assertEqual(restored_analyzer._voltage_reversal_confirmations, 2)
            self.assertAlmostEqual(
                restored_analyzer._last_voltage_reversal_confirmation_s, now, delta=0.01
            )
            self.assertFalse(restored_analyzer._voltage_reversal_emitted)

    def test_stale_or_off_runtime_signal_is_not_restored(self):
        for output_on, observed_at, now in ((False, 1000.0, 1010.0), (True, 1000.0, 1300.0)):
            with self.subTest(output_on=output_on, now=now), tempfile.TemporaryDirectory() as tempdir:
                session_file = os.path.join(tempdir, "charge_session.json")
                original = self._runtime_signal_document(
                    output_on=output_on, observed_at=observed_at
                )
                self._persist_runtime_signal(original, session_file)
                restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
                with patch("charge_logic.SESSION_FILE", session_file), patch(
                    "charge_controller_v2.SESSION_FILE", session_file
                ), patch("production_controller.SESSION_FILE", session_file), patch(
                    "charge_logic.time.time", return_value=now
                ), patch("charge_controller_v2.time.time", return_value=now), patch(
                    "production_controller.time.time", return_value=now
                ):
                    ok, _ = restored.try_restore_session(
                        16.47, 0.66, 1.0, output_is_on=output_on, is_cv=True, is_cc=False
                    )
                self.assertTrue(ok)
                self.assertIsNone(restored._v2_runtime.tracker._analyzer._current_min_a)

    def test_cv_delta_marker_survives_session_restore(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            self._persist_finish_state(session_file, mode="CV")
            with open(session_file, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertTrue(saved["delta_reported"])
            self.assertEqual(saved["delta_trigger_mode"], "CV")
            self.assertEqual(saved["finish_evidence"]["mode"], "CV")
            self.assertAlmostEqual(saved["finish_evidence"]["reference_value"], 0.66)
            self.assertAlmostEqual(saved["finish_evidence"]["accepted_delta"], 0.24)
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1010.0
            ), patch("charge_controller_v2.time.time", return_value=1010.0), patch(
                "production_controller.time.time", return_value=1010.0
            ):
                ok, _ = restored.try_restore_session(
                    16.47, 0.66, 1.0, output_is_on=False, is_cv=True, is_cc=False
                )
            self.assertTrue(ok)
            self.assertTrue(restored._delta_reported)
            self.assertEqual(restored._delta_trigger_mode, "CV")
            self.assertAlmostEqual(restored.finish_timer_start, 900.0)
            self.assertAlmostEqual(restored._finish_evidence["reference_value"], 0.66)
            self.assertAlmostEqual(restored._finish_evidence["accepted_delta"], 0.24)

    def test_cc_delta_marker_survives_session_restore(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            self._persist_finish_state(session_file, mode="CC")
            with open(session_file, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertTrue(saved["delta_reported"])
            self.assertEqual(saved["delta_trigger_mode"], "CC")
            self.assertEqual(saved["finish_evidence"]["mode"], "CC")
            self.assertAlmostEqual(saved["finish_evidence"]["reference_value"], 16.47)
            self.assertAlmostEqual(saved["finish_evidence"]["accepted_delta"], 0.05)
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1010.0
            ), patch("charge_controller_v2.time.time", return_value=1010.0), patch(
                "production_controller.time.time", return_value=1010.0
            ):
                ok, _ = restored.try_restore_session(
                    16.47, 0.66, 1.0, output_is_on=False, is_cv=False, is_cc=True
                )
            self.assertTrue(ok)
            self.assertTrue(restored._delta_reported)
            self.assertEqual(restored._delta_trigger_mode, "CC")
            self.assertAlmostEqual(restored.finish_timer_start, 900.0)
            self.assertAlmostEqual(restored._finish_evidence["reference_value"], 16.47)
            self.assertAlmostEqual(restored._finish_evidence["accepted_delta"], 0.05)

    def test_missing_finish_evidence_keeps_hold_but_marks_provenance_unavailable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            self._persist_finish_state(session_file, mode="CV")
            with open(session_file, "r+", encoding="utf-8") as handle:
                saved = json.load(handle)
                saved.pop("finish_evidence", None)
                handle.seek(0)
                json.dump(saved, handle)
                handle.truncate()
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch("charge_controller_v2.SESSION_FILE", session_file), patch("production_controller.SESSION_FILE", session_file), patch("charge_logic.time.time", return_value=1010.0), patch("charge_controller_v2.time.time", return_value=1010.0), patch("production_controller.time.time", return_value=1010.0):
                ok, _ = restored.try_restore_session(16.47, 0.66, 1.0)
            self.assertTrue(ok)
            self.assertTrue(restored._delta_reported)
            self.assertAlmostEqual(restored.finish_timer_start, 900.0)
            self.assertIsNone(restored._finish_evidence)

    def test_finish_evidence_mode_mismatch_is_discarded(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            self._persist_finish_state(session_file, mode="CV")
            with open(session_file, "r+", encoding="utf-8") as handle:
                saved = json.load(handle)
                saved["finish_evidence"]["mode"] = "CC"
                handle.seek(0)
                json.dump(saved, handle)
                handle.truncate()
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch("charge_controller_v2.SESSION_FILE", session_file), patch("production_controller.SESSION_FILE", session_file), patch("charge_logic.time.time", return_value=1010.0), patch("charge_controller_v2.time.time", return_value=1010.0), patch("production_controller.time.time", return_value=1010.0):
                ok, _ = restored.try_restore_session(16.47, 0.66, 1.0)
            self.assertTrue(ok)
            self.assertTrue(restored._delta_reported)
            self.assertIsNone(restored._finish_evidence)

    def test_safe_wait_state_survives_session_restore(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            controller = self._controller("Ca/Ca", ChargeIntent.RECOVERY, capacity=72)
            controller.current_stage = controller.STAGE_SAFE_WAIT
            controller.stage_start_time = 900.0
            controller._safe_wait_start = 900.0
            controller._safe_wait_next_stage = controller.STAGE_DONE
            controller._safe_wait_target_v = 13.8
            controller._safe_wait_target_i = 1.0
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1000.0
            ), patch("charge_controller_v2.time.time", return_value=1000.0), patch(
                "production_controller.time.time", return_value=1000.0
            ):
                controller._save_session(13.8, 0.0, 1.0)
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1010.0
            ), patch("charge_controller_v2.time.time", return_value=1010.0):
                ok, _ = restored.try_restore_session(13.8, 0.0, 1.0, output_is_on=False)
            self.assertTrue(ok)
            self.assertEqual(restored.current_stage, restored.STAGE_SAFE_WAIT)
            self.assertEqual(restored._safe_wait_next_stage, restored.STAGE_DONE)
            self.assertAlmostEqual(restored._safe_wait_target_v, 13.8)
            self.assertAlmostEqual(restored._safe_wait_start, 900.0)

    def test_delta_marker_without_finish_timer_is_discarded(self):
        document = self._legacy_session(intent=ChargeIntent.RECOVERY)
        document.update({
            "delta_state_version": 1,
            "delta_session_id": "abc123",
            "delta_reported": True,
            "delta_trigger_mode": "CV",
        })
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            with open(session_file, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
            restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=1010.0
            ), patch("charge_controller_v2.time.time", return_value=1010.0):
                ok, _ = restored.try_restore_session(16.47, 0.66, 1.0)
            self.assertTrue(ok)
            self.assertFalse(restored._delta_reported)
            self.assertIsNone(restored._delta_trigger_mode)
            self.assertIsNone(restored.finish_timer_start)

    def test_mode_mismatch_discards_incompatible_extrema(self):
        for saved_mode, observed_mode in (("CV", "CC"), ("CC", "CV")):
            with self.subTest(saved_mode=saved_mode), tempfile.TemporaryDirectory() as tempdir:
                session_file = os.path.join(tempdir, "charge_session.json")
                original = self._runtime_signal_document(mode=saved_mode)
                self._persist_runtime_signal(original, session_file)
                restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
                with patch("charge_logic.SESSION_FILE", session_file), patch(
                    "charge_controller_v2.SESSION_FILE", session_file
                ), patch("production_controller.SESSION_FILE", session_file), patch(
                    "charge_logic.time.time", return_value=1010.0
                ), patch("charge_controller_v2.time.time", return_value=1010.0), patch(
                    "production_controller.time.time", return_value=1010.0
                ):
                    ok, _ = restored.try_restore_session(
                        16.47, 0.66, 1.0, output_is_on=True,
                        is_cv=observed_mode == "CV", is_cc=observed_mode == "CC",
                    )
                self.assertTrue(ok)
                analyzer = restored._v2_runtime.tracker._analyzer
                self.assertIsNone(analyzer._current_min_a)
                self.assertIsNone(analyzer._voltage_max_v)


if __name__ == "__main__":
    unittest.main()
