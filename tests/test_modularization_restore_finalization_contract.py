"""Fake-only contracts for restore_session's current finalization boundary.

These tests describe the existing late apply/finalize order. They do not assert
rollback or claim the partial host mutation is an acceptable target design.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.charge import persistence
from runtime.charge import session_restore as restore_owner
from runtime.charge.session import RestoredSessionDocument
from runtime.charge.session_atomic import WriteStatus, compare_replace_session
from tests.test_modularization_auto_restore_atomic_admission import _Host, _valid_document


class RestoreFinalizationContractTests(unittest.TestCase):
    NOW = 50_000.0

    def restore(self, document, *, configure=None, header=None, normalize=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "session.json"
        preimage = json.dumps(document).encode("utf-8")
        path.write_bytes(preimage)
        host = _Host()
        host._session_file = str(path)
        host._session_restore_snapshot = "old-snapshot"
        host.events = []
        host._save_session = lambda *_args, **_kwargs: (WriteStatus.COMMITTED, preimage)
        if configure:
            configure(host)
        original_capture = RestoredSessionDocument.capture

        def capture(data):
            host.events.append(("snapshot", host._stage_tracking_enabled))
            return original_capture(data)

        def log(*_args, **_kwargs):
            host.events.append(("header", host._stage_tracking_enabled))
            if header:
                return header(host, *_args, **_kwargs)

        def normalizer(_host, data, *, session_file):
            host.events.append(("normalize", host._stage_tracking_enabled))
            if normalize:
                return normalize(host, data, session_file=session_file)
            return False

        with patch("runtime.charge.persistence.time.time", return_value=self.NOW), \
             patch.object(restore_owner, "log_session_header", side_effect=log), \
             patch.object(restore_owner, "_normalize_terminal_done_document", side_effect=normalizer), \
             patch.object(RestoredSessionDocument, "capture", side_effect=capture):
            try:
                result = persistence.restore_session(
                    host, 12.5, 0.0, 0.0, session_file=str(path),
                )
                return host, result, path
            except Exception as exc:
                return host, exc, path

    def test_ordinary_restore_logs_then_captures_snapshot_before_tracking(self):
        host, result, _path = self.restore(_valid_document(saved_at=self.NOW))
        self.assertIsInstance(result, tuple)
        self.assertTrue(result[0])
        self.assertEqual(host.events, [("header", False), ("snapshot", False)])
        self.assertIsInstance(host._session_restore_snapshot, RestoredSessionDocument)
        self.assertTrue(host._stage_tracking_enabled)

    def test_header_exception_keeps_tracking_off_snapshot_old_and_controller_changed(self):
        host, result, _path = self.restore(
            _valid_document(saved_at=self.NOW),
            header=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("header failed")),
        )
        self.assertIsInstance(result, RuntimeError)
        self.assertEqual(str(result), "header failed")
        self.assertEqual(host.events, [("header", False)])
        self.assertFalse(host._stage_tracking_enabled)
        self.assertEqual(host._session_restore_snapshot, "old-snapshot")
        self.assertEqual(host.battery_type, "Ca/Ca")
        self.assertEqual(host.current_stage, host.STAGE_MAIN)

    def test_stage_limit_and_target_failures_precede_header_and_leave_tracking_off(self):
        for method in ("_get_stage_max_hours", "_get_target_v_i"):
            with self.subTest(method=method):
                def configure(host, name=method):
                    setattr(host, name, lambda: (_ for _ in ()).throw(RuntimeError(name + " failed")))
                host, result, _path = self.restore(
                    _valid_document(saved_at=self.NOW), configure=configure,
                )
                self.assertIsInstance(result, RuntimeError)
                self.assertEqual(host.events, [])
                self.assertFalse(host._stage_tracking_enabled)
                self.assertEqual(host._session_restore_snapshot, "old-snapshot")
                self.assertEqual(host.current_stage, host.STAGE_MAIN)

    def test_ambiguous_done_calls_normalizer_and_failure_precedes_snapshot(self):
        document = _valid_document(saved_at=self.NOW, stage="Done")
        host, result, path = self.restore(
            document,
            normalize=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("normalize failed")),
        )
        self.assertIsInstance(result, RuntimeError)
        self.assertEqual(str(result), "normalize failed")
        self.assertEqual(host.events, [("header", False), ("normalize", False)])
        self.assertFalse(host._stage_tracking_enabled)
        self.assertEqual(host._session_restore_snapshot, "old-snapshot")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), document)
        self.assertEqual(host.current_stage, host.STAGE_DONE)

    def test_expired_mix_saves_after_snapshot_and_failed_save_keeps_tracking_off(self):
        def normalize(host, data, *, session_file):
            data["stage"] = "Done"
            host.current_stage = host.STAGE_DONE
            return True

        def configure(host):
            host.stage_start_time = self.NOW - 100
            def fail_save(*_args, **_kwargs):
                host.events.append(("save", host._stage_tracking_enabled,
                                    isinstance(host._session_restore_snapshot, RestoredSessionDocument)))
                raise RuntimeError("terminal save failed")
            host._save_session = fail_save

        document = _valid_document(saved_at=self.NOW, stage=_Host.STAGE_MIX, target_finish_time=self.NOW - 1,
                                   finish_timer_start=self.NOW - 100)
        host, result, path = self.restore(
            document,
            configure=configure,
            normalize=normalize,
        )
        self.assertIsInstance(result, RuntimeError)
        self.assertEqual(str(result), "terminal save failed")
        self.assertEqual(host.events, [("header", False), ("normalize", False),
                                       ("snapshot", False), ("save", False, True)])
        self.assertEqual(sum(event[0] == "save" for event in host.events), 1)
        self.assertEqual(host.current_stage, host.STAGE_DONE)
        self.assertTrue(isinstance(host._session_restore_snapshot, RestoredSessionDocument))
        self.assertFalse(host._stage_tracking_enabled)
        self.assertEqual(path.read_bytes(), json.dumps(document).encode("utf-8"))

    def test_expired_mix_successful_terminal_writer_returns_success_after_snapshot(self):
        save_statuses = []

        def normalize(host, data, *, session_file):
            data["stage"] = "Done"
            host.current_stage = host.STAGE_DONE
            host._normalized_candidate = dict(data)
            return True

        def configure(host):
            host.stage_start_time = self.NOW - 100
            def accept_save(*_args, **_kwargs):
                host.events.append(("save", host._stage_tracking_enabled,
                                    isinstance(host._session_restore_snapshot, RestoredSessionDocument)))
                expected_preimage = _kwargs["restore_expected_bytes"]
                status, persisted = compare_replace_session(
                    host._session_file, expected_preimage, host._normalized_candidate,
                )
                save_statuses.append(status)
                host.saved = status is WriteStatus.COMMITTED
                return status, persisted
            host._save_session = accept_save

        host, result, _path = self.restore(
            _valid_document(saved_at=self.NOW, stage=_Host.STAGE_MIX, target_finish_time=self.NOW - 1,
                            finish_timer_start=self.NOW - 100),
            configure=configure,
            normalize=normalize,
        )
        self.assertTrue(result[0], result)
        self.assertEqual(host.events, [("header", False), ("normalize", False),
                                       ("snapshot", False), ("save", False, True)])
        self.assertEqual(save_statuses, [WriteStatus.COMMITTED])
        self.assertTrue(host.saved)
        self.assertEqual(json.loads(_path.read_text(encoding="utf-8"))["stage"], "Done")
        self.assertTrue(host._stage_tracking_enabled)

    def test_early_native_and_retired_rejection_never_reach_finalizers(self):
        cases = (
            _valid_document(saved_at=self.NOW, native_recipe_selection_v1={"broken": True}),
            _valid_document(saved_at=self.NOW, owner="runtime.charge.persistence", state="retired",
                            schema_version=1, stage="RETIRED",
                            retirement_kind="operator_recovery_clearance", output_intent="verified_off",
                            verified_off_transaction_id="tx", verified_off_recorded_utc="2026-11-12T00:00:00Z",
                            session_id="sid", battery_id="bid", retired_utc="2026-11-12T00:00:00Z"),
        )
        for document in cases:
            with self.subTest(stage=document.get("stage")):
                def install_sentinels(host):
                    def forbidden(name):
                        return lambda *_args, **_kwargs: host.events.append((name,))
                    host._save_session = forbidden("terminal-writer")
                    host._device_set_voltage = forbidden("physical-port")
                    host._device_set_current = forbidden("physical-port")
                    host._set_output = forbidden("physical-port")

                host, result, _path = self.restore(document, configure=install_sentinels)
                self.assertIsInstance(result, tuple)
                self.assertFalse(result[0])
                self.assertEqual(host.events, [])
                self.assertEqual(host.__dict__.get("saved"), None)
                self.assertEqual(host.current_stage, host.STAGE_IDLE)

    def test_terminal_normalizer_builds_candidate_without_canonical_write(self):
        document = {"stage": "Done", "unknown_extension": {"keep": True}}
        host = _Host()
        with patch("runtime.charge.session_atomic.complete_session_document",
                   side_effect=lambda _host, candidate, **_kw: candidate), \
             patch.object(persistence, "atomic_session_write") as write:
            result = persistence._normalize_terminal_done_document(
                host, document, session_file="unused",
            )
        self.assertTrue(result)
        self.assertEqual(document["unknown_extension"], {"keep": True})
        self.assertEqual(document["output_intent"], persistence.DONE_OUTPUT_OFF)
        write.assert_not_called()

    def test_restore_save_propagates_typed_cas_result_without_swallowing(self):
        candidate = {"stage": "MAIN", "unknown_extension": 3}
        expected = b'{"stage":"MAIN"}'
        with patch.object(persistence, "project_session_document", return_value=candidate), \
             patch("runtime.charge.session_atomic.compare_replace_session",
                   return_value=(WriteStatus.NOT_COMMITTED, expected)) as cas:
            result = persistence.save_session(
                _Host(), 12.5, 0.0, 0.0, session_file="session.json",
                restore_expected_bytes=expected,
            )
        self.assertEqual(result, (WriteStatus.NOT_COMMITTED, expected))
        cas.assert_called_once_with(
            "session.json", expected, candidate, allow_nan=True,
        )

    def test_failed_commit_preserves_bytes_for_next_restore_admission(self):
        document = _valid_document(saved_at=self.NOW)
        preimage = json.dumps(document).encode("utf-8")
        host, result, path = self.restore(
            document,
            configure=lambda target: setattr(
                target, "_save_session",
                lambda *_args, **_kwargs: (WriteStatus.NOT_COMMITTED, preimage),
            ),
        )
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("NOT_COMMITTED", str(result))
        self.assertFalse(host._stage_tracking_enabled)
        self.assertEqual(path.read_bytes(), preimage)

        next_host = _Host()
        next_host._save_session = lambda *_args, **_kwargs: (WriteStatus.COMMITTED, preimage)
        with patch("runtime.charge.persistence.time.time", return_value=self.NOW), \
             patch.object(restore_owner, "log_session_header"):
            accepted, _message = persistence.restore_session(
                next_host, 12.5, 0.0, 0.0, session_file=str(path),
            )
        self.assertTrue(accepted)
        self.assertEqual(path.read_bytes(), preimage)

if __name__ == "__main__":
    unittest.main()
