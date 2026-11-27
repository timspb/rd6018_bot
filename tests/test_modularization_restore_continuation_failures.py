"""Fake-only evidence for late restore_session continuation failure cuts.

These tests pin current diagnostic behavior. Late collaborator exceptions may
leave a partially restored host; this module does not assert rollback.
"""
import json
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from runtime.charge import persistence
from runtime.charge import session_restore as restore_owner
from runtime.charge.persistence import restore_session
from tests.test_modularization_auto_restore_atomic_admission import _Host, _valid_document


class _BrokenDeque:
    maxlen = 8

    def clear(self):
        raise RuntimeError("deque clear exploded")

    def extend(self, _items):
        raise AssertionError("extend should not be reached")


class RestoreContinuationFailureDiagnostics(unittest.TestCase):
    NOW = 50_000.0

    def run_cut(self, document=None, *, host_change=None, patcher=None):
        document = _valid_document(saved_at=self.NOW) if document is None else document
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            original_bytes = path.read_bytes()
            host = _Host()
            host.total_start_time = 1.0
            host.battery_type = "before"
            host.ah_capacity = 12.0
            host._session_restore_snapshot = "old-snapshot"
            if host_change:
                host_change(host)
            before = dict(host.__dict__)
            ctx = patcher() if patcher else nullcontext()
            with patch("runtime.charge.persistence.time.time", return_value=self.NOW), ctx:
                with self.assertRaises(RuntimeError) as raised:
                    restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))
            changed = sorted(
                key for key in set(before) | set(host.__dict__)
                if before.get(key, object()) != host.__dict__.get(key, object())
            )
            return raised.exception, host, changed, path.read_bytes() != original_bytes

    def assert_late_cut(self, outcome, host, changed, file_changed, *, expected_snapshot):
        self.assertIsInstance(outcome, RuntimeError)
        self.assertTrue(changed, "late failure unexpectedly had no host mutation")
        self.assertIn("current_stage", changed)
        self.assertIn("battery_type", changed)
        self.assertIn("ah_capacity", changed)
        # The deque can mutate in place, so __dict__ identity comparison cannot track it.
        self.assertIn("previous_stage", changed)
        self.assertFalse(host._stage_tracking_enabled)
        self.assertEqual(host._session_restore_snapshot != "old-snapshot", expected_snapshot)
        self.assertFalse(file_changed)

    def test_reset_delta_exception_after_state_and_history_apply(self):
        def break_reset(host):
            host._reset_delta_and_blanking = lambda _now: (_ for _ in ()).throw(
                RuntimeError("reset exploded")
            )
        outcome, host, changed, file_changed = self.run_cut(host_change=break_reset)
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)
        self.assertEqual(host.current_stage, host.STAGE_MAIN)
        self.assertEqual(host.battery_type, "Ca/Ca")

    def test_stage_limit_getter_exception_is_late(self):
        def break_getter(host):
            host._get_stage_max_hours = lambda: (_ for _ in ()).throw(RuntimeError("limit exploded"))
        outcome, host, changed, file_changed = self.run_cut(host_change=break_getter)
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)
        self.assertTrue(hasattr(host, "reset_called"))

    def test_target_getter_exception_is_late(self):
        def break_getter(host):
            host._get_target_v_i = lambda: (_ for _ in ()).throw(RuntimeError("target exploded"))
        outcome, host, changed, file_changed = self.run_cut(host_change=break_getter)
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)

    def test_rules_summary_exception_is_late(self):
        def break_summary(host):
            host._session_rules_summary = lambda: (_ for _ in ()).throw(RuntimeError("rules exploded"))
        outcome, host, changed, file_changed = self.run_cut(host_change=break_summary)
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)

    def test_header_logger_exception_is_late(self):
        outcome, host, changed, file_changed = self.run_cut(
            patcher=lambda: patch.object(
                restore_owner, "log_session_header",
                side_effect=RuntimeError("header exploded"),
            ),
        )
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)

    def test_faulty_deque_clear_is_after_other_host_fields_apply(self):
        outcome, host, changed, file_changed = self.run_cut(
            _valid_document(saved_at=self.NOW, stage_history=[{"stage": "Main Charge"}]),
            host_change=lambda host: setattr(host, "_stage_history", _BrokenDeque()),
        )
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)
        self.assertEqual(host.battery_type, "Ca/Ca")

    def test_terminal_normalization_exception_precedes_snapshot_and_file_write(self):
        document = _valid_document(saved_at=self.NOW, stage="Done")
        outcome, host, changed, file_changed = self.run_cut(
            document,
            patcher=lambda: patch.object(
                restore_owner, "_normalize_terminal_done_document",
                side_effect=RuntimeError("normalization exploded"),
            ),
        )
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=False)
        self.assertEqual(host.current_stage, host.STAGE_DONE)

    def test_expired_mix_save_exception_happens_after_snapshot(self):
        document = _valid_document(
            saved_at=self.NOW, stage="Mix", target_finish_time=self.NOW - 1,
            finish_timer_start=self.NOW - 100,
        )
        def break_save(host):
            host._save_session = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("save exploded"))
        outcome, host, changed, file_changed = self.run_cut(document, host_change=break_save)
        self.assert_late_cut(outcome, host, changed, file_changed, expected_snapshot=True)
        self.assertEqual(host.current_stage, host.STAGE_DONE)

    def test_native_and_retired_rejections_remain_zero_mutation(self):
        cases = (
            _valid_document(saved_at=self.NOW, native_recipe_selection_v1={"broken": True}),
            _valid_document(
                saved_at=self.NOW, owner="runtime.charge.persistence", state="retired",
                schema_version=1, stage="RETIRED", retirement_kind="operator_recovery_clearance",
                output_intent="verified_off", verified_off_transaction_id="tx",
                verified_off_recorded_utc="2026-11-12T00:00:00Z", session_id="sid",
                battery_id="bid", retired_utc="2026-11-12T00:00:00Z",
            ),
        )
        for document in cases:
            with self.subTest(stage=document.get("stage")):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "session.json"
                    path.write_text(json.dumps(document), encoding="utf-8")
                    host = _Host()
                    before = dict(host.__dict__)
                    with patch("runtime.charge.persistence.time.time", return_value=self.NOW):
                        result = restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))
                    self.assertFalse(result[0])
                    self.assertEqual(host.__dict__, before)

    def test_timeline_projection_failure_is_before_host_apply(self):
        document = _valid_document(saved_at=self.NOW, stage="Mix")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            host = _Host()
            host.total_start_time = 1.0
            host.battery_type = "before"
            host.ah_capacity = 12.0
            host._session_restore_snapshot = "old-snapshot"
            before = dict(host.__dict__)
            with patch("runtime.charge.persistence.time.time", return_value=self.NOW), \
                 patch.object(restore_owner, "project_restore_stage_timeline",
                              side_effect=RuntimeError("timeline projection exploded")):
                with self.assertRaisesRegex(RuntimeError, "timeline projection exploded"):
                    restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))
            self.assertEqual(host.__dict__, before)


if __name__ == "__main__":
    unittest.main()
