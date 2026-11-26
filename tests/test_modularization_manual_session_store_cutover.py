import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import manual_mode
from manual_mode import ManualSessionManager, ManualSessionState
from runtime.charge import manual_session_store


class ManualSessionStoreCutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "manual_session_v2.json"

    def manager(self):
        fake_port = SimpleNamespace(enable=mock.AsyncMock())
        with mock.patch.object(manual_mode, "get_or_create_execution_port", return_value=fake_port):
            return ManualSessionManager(SimpleNamespace(), session_file=str(self.path))

    def document(self, state="stopped", request=None, identity=None):
        return {
            "version": 2,
            "state": state,
            "request": request,
            "started_at": 123.5,
            "paused_total_s": 4.0,
            "cooling_started_at": 99.0,
            "stop_reason": "",
            "phase_transition_reason": "",
            "finish_hold_started_at": None,
            "saved_at": 130.0,
            "session_identity": identity,
        }

    def request(self):
        return {
            "voltage_v": 14.4,
            "current_a": 5.0,
            "stop": {},
            "battery_id": "test-battery",
            "capacity_ah": None,
            "notes": "test",
            "profile": None,
            "stage": "main",
        }

    def test_v2_round_trip_and_document_shape_remain_owned_by_manager(self):
        manager = self.manager()
        manager.request = manual_mode.ManualChargeRequest(14.4, 5.0, battery_id="test-battery")
        with mock.patch.object(manual_mode.time, "time", return_value=12345.0):
            expected = manager._document()
            manager._persist()
        self.assertEqual(manual_session_store.read_manual_session_document(self.path), expected)
        self.assertEqual(expected["version"], 2)
        self.assertEqual(set(expected), {
            "version", "state", "request", "started_at", "paused_total_s",
            "cooling_started_at", "stop_reason", "phase_transition_reason",
            "finish_hold_started_at", "saved_at", "session_identity",
        })

    def test_active_arming_and_cooling_restore_as_interrupted_without_enable(self):
        for state in ("active", "arming", "cooling"):
            with self.subTest(state=state):
                self.path.write_text(json.dumps(self.document(state, self.request())), encoding="utf-8")
                manager = self.manager()
                self.assertEqual(manager.state, ManualSessionState.INTERRUPTED)
                self.assertEqual(manager.request.voltage_v, 14.4)
                self.assertEqual(manager.stop_reason, "process_restart_requires_operator_reauthorization")
                self.assertIsNone(manager.cooling_started_at)
                self.assertFalse(getattr(manager.execution_port, "enable", mock.Mock()).called)

    def test_malformed_roots_corrupt_json_and_invalid_request_are_safe(self):
        for content in ("[]", '"text"', "42", "null", "{"):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                manager = self.manager()
                self.assertEqual(manager.state, ManualSessionState.IDLE)
        self.path.write_text(json.dumps(self.document("active", {"voltage_v": "bad"})), encoding="utf-8")
        manager = self.manager()
        self.assertEqual(manager.state, ManualSessionState.INTERRUPTED)
        self.assertIsNone(manager.request)

    def test_invalid_identity_is_logged_and_does_not_prevent_restart_containment(self):
        self.path.write_text(json.dumps(self.document("active", self.request(), ["bad"])), encoding="utf-8")
        manager = self.manager()
        self.assertEqual(manager.state, ManualSessionState.INTERRUPTED)
        self.assertEqual(manager.identity_restore_resolution, "AMBIGUOUS")

    def test_writer_oserror_is_swallowed_and_prior_document_is_preserved(self):
        self.path.write_text('{"prior": true}', encoding="utf-8")
        manager = self.manager()
        with mock.patch.object(manual_mode, "write_manual_session_document", side_effect=OSError("disk error")):
            manager._persist()
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"prior": true}')

    def test_ast_confirms_single_store_writer_and_no_direct_file_json_io(self):
        source = Path(manual_mode.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ManualSessionManager")
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        persist = methods["_persist"]
        calls = [n for n in ast.walk(persist) if isinstance(n, ast.Call)]
        self.assertEqual(sum(isinstance(n.func, ast.Name) and n.func.id == "write_manual_session_document" for n in calls), 1)
        restore = methods["_restore_as_interrupted"]
        restore_calls = [n for n in ast.walk(restore) if isinstance(n, ast.Call)]
        self.assertEqual(sum(isinstance(n.func, ast.Name) and n.func.id == "read_manual_session_document" for n in restore_calls), 1)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"dump", "load", "open"} for n in ast.walk(cls)))


if __name__ == "__main__":
    unittest.main()
