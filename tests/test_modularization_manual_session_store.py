import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.charge import manual_session_store as store


class ManualSessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)
        self.path = self.directory / "manual_session_v2.json"

    def legacy_document(self):
        return {
            "version": 2,
            "state": "active",
            "request": {"battery_id": "Тест", "profile": {"name": "Аккумулятор"}},
            "started_at": 12.5,
            "paused_total_s": 1.25,
            "cooling_started_at": None,
            "stop_reason": "",
            "phase_transition_reason": "",
            "finish_hold_started_at": None,
            "saved_at": 15.75,
            "session_identity": {"session_id": "abc", "extra": [1, None]},
        }

    def test_all_legacy_keys_round_trip_with_legacy_json_format(self):
        document = self.legacy_document()
        expected = json.dumps(document, ensure_ascii=False, indent=2)
        store.write_manual_session_document(self.path, document)
        self.assertEqual(self.path.read_text(encoding="utf-8"), expected)
        self.assertEqual(store.read_manual_session_document(self.path), document)
        self.assertEqual(len(document), 11)

    def test_missing_file_returns_none(self):
        self.assertIsNone(store.read_manual_session_document(self.path))

    def test_truncated_json_returns_none(self):
        self.path.write_text('{"state":', encoding="utf-8")
        self.assertIsNone(store.read_manual_session_document(self.path))

    def test_non_mapping_json_roots_return_none(self):
        for raw in ("[]", '"text"', "42", "null"):
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                self.assertIsNone(store.read_manual_session_document(self.path))

    def test_read_permission_or_io_error_returns_none(self):
        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            self.assertIsNone(store.read_manual_session_document(self.path))

    def test_non_mapping_writer_does_not_replace_existing_target(self):
        self.path.write_text("old", encoding="utf-8")
        with self.assertRaises(TypeError):
            store.write_manual_session_document(self.path, [("not", "mapping")])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old")

    def test_replace_failure_preserves_target_and_removes_temp_file(self):
        self.path.write_text("old", encoding="utf-8")
        with mock.patch.object(store.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                store.write_manual_session_document(self.path, self.legacy_document())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old")
        self.assertEqual(list(self.directory.glob("*.tmp")), [])
        self.assertEqual(list(self.directory.glob(".*.tmp")), [])

    def test_tempfile_uses_target_directory_and_file_fsync_runs(self):
        real_mkstemp = store.tempfile.mkstemp
        created = {}

        def capture_mkstemp(*args, **kwargs):
            created["dir"] = Path(kwargs["dir"])
            result = real_mkstemp(*args, **kwargs)
            created["path"] = Path(result[1])
            return result

        with mock.patch.object(store.tempfile, "mkstemp", side_effect=capture_mkstemp):
            with mock.patch.object(store.os, "fsync", wraps=store.os.fsync) as fsync:
                store.write_manual_session_document(self.path, self.legacy_document())
        self.assertEqual(created["dir"], self.directory)
        self.assertEqual(created["path"].parent, self.directory)
        self.assertGreaterEqual(fsync.call_count, 1)

    def test_module_import_has_no_filesystem_or_actuator_side_effects(self):
        with mock.patch.object(store.tempfile, "mkstemp") as mkstemp, mock.patch.object(
            store.os, "replace"
        ) as replace:
            importlib.reload(store)
        mkstemp.assert_not_called()
        replace.assert_not_called()


if __name__ == "__main__":
    unittest.main()
