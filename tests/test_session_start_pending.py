import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.charge import persistence, session_atomic, start_pending


class StartPendingPersistenceTests(unittest.TestCase):
    def test_persistence_exports_the_canonical_start_pending_owner_objects(self):
        names = (
            "START_PENDING_KEY", "StartPendingAction", "StartPendingResult",
            "StartPendingStatus", "_pending_start_document", "begin_start_pending",
            "finish_start_pending", "read_start_pending",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(persistence, name), getattr(start_pending, name))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "charge_session.json"

    def tearDown(self):
        self.tmp.cleanup()

    def begin(self, prior=None):
        if prior is not None:
            self.path.write_bytes(prior)
        return persistence.begin_start_pending(
            {"stage": "CC", "target_voltage": 14.2},
            transaction_id="txn-1", path=self.path,
        )

    def test_begin_and_exact_rollback_existing_bytes_generation_and_hash(self):
        prior = b'{\n  "stage": "MAIN",\n  "start_transaction_generation": 7\n}\n'
        result = self.begin(prior)
        self.assertEqual(result.status, persistence.StartPendingStatus.COMMITTED)
        self.assertEqual(result.pending["generation"], 8)
        self.assertEqual(result.pending["previous_generation"], 7)
        self.assertEqual(result.pending["previous_sha256"], hashlib.sha256(prior).hexdigest())
        rollback = persistence.finish_start_pending(
            result.pending_raw, result.pending, action=persistence.StartPendingAction.ROLLBACK,
            path=self.path,
        )
        self.assertEqual(rollback.status, persistence.StartPendingStatus.COMMITTED)
        self.assertEqual(self.path.read_bytes(), prior)

    def test_absent_file_begin_commit_and_rollback_to_absence(self):
        result = self.begin()
        self.assertEqual(result.status, persistence.StartPendingStatus.COMMITTED)
        self.assertFalse(result.pending["previous_exists"])
        rollback = persistence.finish_start_pending(
            result.pending_raw, result.pending, action=persistence.StartPendingAction.ROLLBACK,
            path=self.path,
        )
        self.assertEqual(rollback.status, persistence.StartPendingStatus.COMMITTED)
        self.assertFalse(self.path.exists())

        result = self.begin()
        committed = persistence.finish_start_pending(
            result.pending_raw, result.pending, dict(result.pending['candidate']), path=self.path,
        )
        self.assertEqual(committed.status, persistence.StartPendingStatus.COMMITTED)
        self.assertEqual(json.loads(self.path.read_text())["start_transaction_generation"], 1)
        self.assertEqual(self.path.read_bytes(), committed.observed_raw)

    def test_reject_stale_pending_bytes_and_wrong_transaction_identity(self):
        result = self.begin(b'{"stage":"MAIN"}')
        stale = persistence.finish_start_pending(
            b"stale", result.pending, {"stage": "CC"}, path=self.path,
        )
        wrong = persistence.finish_start_pending(
            result.pending_raw, {**result.pending, "transaction_id": "wrong"},
            {"stage": "CC"}, path=self.path,
        )
        self.assertEqual(stale.status, persistence.StartPendingStatus.OUTCOME_UNCERTAIN)
        self.assertEqual(wrong.status, persistence.StartPendingStatus.NOT_COMMITTED)
        self.assertTrue(persistence.read_start_pending(self.path)[1])

    def test_malformed_json_and_unknown_transaction_envelope_fail_closed(self):
        self.path.write_bytes(b"{")
        self.assertEqual(self.begin().status, persistence.StartPendingStatus.OUTCOME_UNCERTAIN)
        with self.assertRaises(PermissionError):
            session_atomic.atomic_session_write(self.path, {"stage": "CC"})
        self.path.write_text('{"start_transaction_future_v9": {}}')
        with self.assertRaises(PermissionError):
            session_atomic.atomic_session_write(self.path, {"stage": "CC"})
        self.assertFalse(persistence.restore_session(object(), 0, 0, 0, session_file=str(self.path))[0])

    def test_ordinary_writers_blocked_during_pending(self):
        result = self.begin(b'{"stage":"MAIN"}')
        before = self.path.read_bytes()
        persistence.save_session(object(), 0, 0, 0, session_file=str(self.path))
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(PermissionError):
            session_atomic.atomic_session_write(self.path, {"stage": "CC"})
        persistence.clear_session_file(object(), session_file=str(self.path))
        self.assertTrue(self.path.exists())
        self.assertEqual(persistence.mark_session_interrupted(
            str(self.path), expected_document_sha256="bad", expected_identity={},
            recorded_at_utc="now",
        ), False)
        self.assertFalse(persistence.enrich_restored_session(
            type("Host", (), {"current_stage": "CC", "STAGE_IDLE": "IDLE"})(),
            {"stage": "CC"}, session_file=str(self.path),
        ))
        host = type("Host", (), {"STAGE_IDLE": "IDLE", "current_stage": "IDLE"})()
        self.assertFalse(persistence.retire_controller_session(
            host, session_id="s", battery_id="b", off_transaction_id="off",
            session_file=str(self.path),
        ))
        self.assertTrue(self.path.exists())

    def test_compare_delete_cannot_remove_concurrently_replaced_pending(self):
        self.path.write_text('{"stage":"MAIN"}')
        expected = self.path.read_bytes()
        persistence.begin_start_pending(
            {"stage": "CC"}, transaction_id="racing", path=self.path,
        )
        self.assertEqual(session_atomic.compare_delete_session(self.path, expected), "NOT_COMMITTED")
        self.assertTrue(self.path.exists())
        self.assertEqual(persistence.read_start_pending(self.path)[1]["transaction_id"], "racing")

    def test_begin_cut_before_replace_and_after_replace_fsync_classification(self):
        self.path.write_bytes(b'{"stage":"MAIN"}')
        with mock.patch.object(session_atomic, "_atomic_bytes_replace_locked", side_effect=OSError("before")):
            result = persistence.begin_start_pending({"stage": "CC"}, transaction_id="before", path=self.path)
        self.assertEqual(result.status, persistence.StartPendingStatus.NOT_COMMITTED)
        self.assertEqual(self.path.read_bytes(), b'{"stage":"MAIN"}')

        real_replace = session_atomic._atomic_bytes_replace_locked
        def replace_then_fail_dir(target, payload):
            real_replace(target, payload)
            raise OSError("after replace / directory durability uncertain")
        with mock.patch.object(session_atomic, "_atomic_bytes_replace_locked", side_effect=replace_then_fail_dir):
            result = persistence.begin_start_pending({"stage": "CC"}, transaction_id="after", path=self.path)
        self.assertEqual(result.status, persistence.StartPendingStatus.COMMITTED)
        self.assertEqual(result.pending["transaction_id"], "after")

    def test_unexpected_readback_classifies_uncertain(self):
        self.path.write_bytes(b'{"stage":"MAIN"}')
        with mock.patch.object(session_atomic, "_atomic_bytes_replace_locked",
                                side_effect=lambda target, payload: target.write_bytes(b'{"other":true}')):
            result = persistence.begin_start_pending({"stage": "CC"}, transaction_id="uncertain", path=self.path)
        self.assertEqual(result.status, persistence.StartPendingStatus.OUTCOME_UNCERTAIN)

    def test_compare_replace_typed_status_and_exact_preimage_after_pre_replace_failure(self):
        prior = b'{"stage":"MAIN"}\r\n'
        self.path.write_bytes(prior)
        with mock.patch.object(session_atomic, "_atomic_session_write_locked",
                               side_effect=OSError("before replace")):
            status, observed = session_atomic.compare_replace_session(
                self.path, prior, {"stage": "DONE"},
            )
        self.assertIs(status, session_atomic.WriteStatus.NOT_COMMITTED)
        self.assertEqual(observed, prior)
        self.assertEqual(self.path.read_bytes(), prior)

    def test_compare_replace_candidate_and_exact_noop(self):
        prior = b'{"stage":"MAIN"}'
        self.path.write_bytes(prior)
        with mock.patch.object(session_atomic, "_atomic_bytes_replace_locked") as replace:
            status, observed = session_atomic.compare_replace_session(
                self.path, prior, {"stage": "MAIN"}, replacement_bytes=prior,
            )
        self.assertIs(status, session_atomic.WriteStatus.COMMITTED)
        self.assertEqual(observed, prior)
        replace.assert_not_called()

        status, observed = session_atomic.compare_replace_session(
            self.path, prior, {"stage": "DONE"}, replacement_bytes=b'{"stage":"DONE"}',
        )
        self.assertIs(status, session_atomic.WriteStatus.COMMITTED)
        self.assertEqual(observed, b'{"stage":"DONE"}')

    def test_compare_replace_readback_unavailable_is_uncertain(self):
        prior = b'{"stage":"MAIN"}'
        self.path.write_bytes(prior)
        real_read_bytes = Path.read_bytes
        calls = {"count": 0}
        real_replace = session_atomic._atomic_session_write_locked
        replacements = {"count": 0}
        def fail_readback(path):
            calls["count"] += 1
            if calls["count"] == 3:
                raise OSError("readback unavailable")
            return real_read_bytes(path)
        def count_replace(*args, **kwargs):
            replacements["count"] += 1
            return real_replace(*args, **kwargs)
        with mock.patch.object(Path, "read_bytes", fail_readback), \
             mock.patch.object(session_atomic, "_atomic_session_write_locked", side_effect=count_replace):
            status, observed = session_atomic.compare_replace_session(
                self.path, prior, {"stage": "DONE"},
            )
        self.assertIs(status, session_atomic.WriteStatus.OUTCOME_UNCERTAIN)
        self.assertIsNone(observed)
        self.assertEqual(calls["count"], 3)
        self.assertEqual(replacements["count"], 1)

    def test_compare_replace_unrecognized_readback_is_uncertain(self):
        prior = b'{"stage":"MAIN"}'
        self.path.write_bytes(prior)
        with mock.patch.object(session_atomic, "_atomic_bytes_replace_locked",
                               side_effect=lambda target, _payload: target.write_bytes(b'{"stage":"OTHER"}')):
            status, observed = session_atomic.compare_replace_session(
                self.path, prior, {"stage": "DONE"},
            )
        self.assertIs(status, session_atomic.WriteStatus.OUTCOME_UNCERTAIN)
        self.assertEqual(observed, b'{"stage":"OTHER"}')


if __name__ == "__main__":
    unittest.main()
