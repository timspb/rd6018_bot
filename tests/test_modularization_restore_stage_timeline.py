"""Fake-only contracts for AUTO restore stage continuation projection."""

import inspect
import unittest
from unittest.mock import patch

from runtime.charge import persistence
from runtime.charge.restore_projection import project_restore_stage_timeline
from tests.test_modularization_auto_restore_atomic_admission import (
    _Host,
    _valid_document,
)
import json
import tempfile
from pathlib import Path


class RestoreStageTimelineProjectionTests(unittest.TestCase):
    NOW = 50_000.0

    def project(self, stage, target_finish, *, saved=49_000.0, finish=None):
        return project_restore_stage_timeline(
            current_stage=stage,
            main_stage=_Host.STAGE_MAIN,
            mix_stage=_Host.STAGE_MIX,
            desulfation_stage=_Host.STAGE_DESULFATION,
            done_stage=_Host.STAGE_DONE,
            now=self.NOW,
            target_finish_time=target_finish,
            saved_stage_start=saved,
            existing_finish_timer_start=finish,
            mix_done_timer=7_200.0,
        )

    def test_no_target_finish_uses_valid_saved_time_or_now_and_preserves_stage(self):
        for stage in (_Host.STAGE_MAIN, _Host.STAGE_MIX, _Host.STAGE_DESULFATION,
                      _Host.STAGE_DONE, _Host.STAGE_SAFE_WAIT):
            with self.subTest(stage=stage):
                result = self.project(stage, None)
                self.assertEqual(result.stage, stage)
                self.assertEqual(result.stage_start_time, 49_000.0)
                self.assertEqual(result.remaining_min, 0)
        self.assertEqual(self.project(_Host.STAGE_SAFE_WAIT, None, saved=0).stage_start_time, self.NOW)

    def test_future_stages_and_mix_clock_semantics(self):
        future = self.NOW + 125.9
        for stage in (_Host.STAGE_MAIN, _Host.STAGE_DONE, _Host.STAGE_SAFE_WAIT):
            with self.subTest(stage=stage):
                result = self.project(stage, future)
                self.assertEqual(result.stage, stage)
                self.assertEqual(result.stage_start_time, 49_000.0)
                self.assertEqual(result.remaining_min, 2)
        no_finish = self.project(_Host.STAGE_MIX, future)
        self.assertEqual(no_finish.stage_start_time, 49_000.0)
        self.assertFalse(no_finish.update_finish_timer_start)
        with_finish = self.project(_Host.STAGE_MIX, future, finish=48_000.0)
        self.assertIsNone(with_finish.stage_start_time)
        self.assertTrue(with_finish.update_finish_timer_start)
        self.assertEqual(with_finish.finish_timer_start, future - 7_200.0)
        self.assertEqual(with_finish.remaining_min, 2)

    def test_future_desulfation_retains_two_hour_phase_formula(self):
        future = self.NOW + 900.0
        result = self.project(_Host.STAGE_DESULFATION, future)
        self.assertEqual(result.stage_start_time, self.NOW - (2 * 3600 - 900.0))

    def test_expired_transitions_and_zero_threshold(self):
        for target in (self.NOW, self.NOW - 0.1):
            with self.subTest(target=target):
                mix = self.project(_Host.STAGE_MIX, target)
                self.assertEqual(mix.stage, _Host.STAGE_DONE)
                self.assertTrue(mix.clear_restored_targets)
                self.assertTrue(mix.restored_terminal)
                self.assertEqual(mix.stage_start_time, self.NOW)
                self.assertEqual(mix.remaining_min, 0)
                desulfation = self.project(_Host.STAGE_DESULFATION, target)
                self.assertEqual(desulfation.stage, _Host.STAGE_MAIN)
                self.assertTrue(desulfation.clear_restored_targets)
                self.assertFalse(desulfation.restored_terminal)
                self.assertEqual(desulfation.stage_start_time, self.NOW)
                main = self.project(_Host.STAGE_MAIN, target)
                self.assertEqual(main.stage, _Host.STAGE_MAIN)
                self.assertIsNone(main.stage_start_time)
                self.assertFalse(main.clear_restored_targets)

    def test_projector_has_no_host_clock_or_io_access(self):
        source = inspect.getsource(project_restore_stage_timeline)
        for forbidden in ("time.time", "datetime", "open(", "Path(", "os.", "host."):
            self.assertNotIn(forbidden, source)


class RestoreStageTimelineIntegrationTests(unittest.TestCase):
    NOW = RestoreStageTimelineProjectionTests.NOW

    def restore(self, document, *, stage_start=49_000.0, finish=48_000.0):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            host = _Host()
            host.stage_start_time = stage_start
            host.finish_timer_start = finish
            with patch("runtime.charge.persistence.time.time", return_value=self.NOW):
                return host, persistence.restore_session(
                    host, 12.5, 0.0, 0.0, session_file=str(path),
                )

    def test_actual_restore_applies_future_mix_projection_and_exact_message(self):
        target = self.NOW + 125.9
        host, (accepted, message) = self.restore(_valid_document(
            saved_at=self.NOW, stage="Mix", target_finish_time=target,
            finish_timer_start=48_000.0, stage_start_time=49_000.0,
        ))
        self.assertTrue(accepted)
        self.assertEqual(host.current_stage, _Host.STAGE_MIX)
        self.assertEqual(host.stage_start_time, 49_000.0)
        self.assertEqual(host.finish_timer_start, target - persistence.MIX_DONE_TIMER)
        self.assertIn("Осталось времени: <code>2</code> мин.", message)
        self.assertIn("Цель: <code>14.4</code>В / <code>1.00</code>А", message)

    def test_actual_expired_mix_transitions_done_and_preserves_transition_copy(self):
        host, (accepted, message) = self.restore(_valid_document(
            saved_at=self.NOW, stage="Mix", target_finish_time=self.NOW,
            finish_timer_start=48_000.0,
        ))
        self.assertTrue(accepted)
        self.assertEqual(host.current_stage, _Host.STAGE_DONE)
        self.assertTrue(host.saved)
        self.assertIn("Переход к следующей фазе: <code>Done</code>.", message)

    def test_actual_missing_finish_keeps_safe_wait_stage_and_message_shape(self):
        host, (accepted, message) = self.restore(_valid_document(
            saved_at=self.NOW, stage="Safe Wait", stage_start_time=49_000.0,
        ))
        self.assertTrue(accepted)
        self.assertEqual(host.current_stage, _Host.STAGE_SAFE_WAIT)
        self.assertEqual(host.stage_start_time, 49_000.0)
        self.assertIn("Продолжаю режим: <code>Safe Wait</code>.", message)
        self.assertNotIn("Осталось времени:", message)


if __name__ == "__main__":
    unittest.main()
