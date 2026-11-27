"""Fake-only regressions for atomic pre-apply trace identity restore."""

import tempfile
import time
import unittest
import uuid
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.charge.persistence import restore_session
from tests.test_modularization_auto_restore_atomic_admission import (
    _Host,
    _valid_document,
)


class _Intent(str, Enum):
    NORMAL = "normal"
    DIAGNOSTIC = "diagnostic"


class _Condition(str, Enum):
    UNKNOWN = "unknown"


class _BrokenString:
    def __str__(self):
        raise RuntimeError("string conversion exploded")


class _FailingIntent:
    def __init__(self, value):
        if value == "normal":
            raise RuntimeError("intent conversion exploded")
        self.value = value


def _host():
    host = _Host()
    host.total_start_time = 7.0
    host.battery_type = "old-profile"
    host.ah_capacity = 12.0
    host._v2_battery_id = "pre-restore-battery"
    host._v2_intent = _Intent.DIAGNOSTIC
    host._v2_condition_before = _Condition.UNKNOWN
    host.host_configuration = SimpleNamespace(
        restore_trace_default_intent=_Intent.NORMAL,
        restore_trace_default_condition=_Condition.UNKNOWN,
    )
    return host


class TracePreapplyCutoverTests(unittest.TestCase):
    def _restore(self, document, *, host=None, patch_json=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text("{}", encoding="utf-8")
            target = _host() if host is None else host
            before = dict(target.__dict__)
            if patch_json:
                with patch("runtime.charge.persistence.json.loads", return_value=document):
                    outcome = restore_session(
                        target, 12.5, 0.0, 0.0, session_file=str(path),
                    )
            else:
                import json
                path.write_text(json.dumps(document), encoding="utf-8")
                with patch("runtime.charge.persistence.time.time", return_value=50_000.0):
                    outcome = restore_session(
                        target, 12.5, 0.0, 0.0, session_file=str(path),
                    )
            return target, before, outcome

    def test_missing_id_and_invalid_time_use_future_restored_identity_context(self):
        document = _valid_document(
            profile="EFB", ah_limit=80, total_start_time=49_000.0,
            v2_trace_session_id="", v2_trace_started_at="invalid", saved_at=50_000,
            v2_battery_id="", v2_intent="diagnostic",
        )
        host, _, outcome = self._restore(document)
        self.assertTrue(outcome[0], outcome)
        expected_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "rd6018-recovery:EFB|80|49000.000000|50000",
        ).hex
        self.assertEqual(host._v2_trace_session_id, expected_id)
        self.assertEqual(host._v2_trace_started_at, 49_000.0)
        self.assertEqual(host.battery_type, "EFB")
        self.assertEqual(host.ah_capacity, 80.0)
        self.assertEqual(host._v2_battery_id, "pre-restore-battery")
        self.assertIs(host._v2_intent, _Intent.DIAGNOSTIC)

    def test_missing_trace_time_uses_future_total_start_and_explicit_id_is_kept(self):
        document = _valid_document(
            profile="AGM", ah_limit=55, total_start_time=49_100.0,
            v2_trace_session_id=" legacy-id ", saved_at=50_000,
        )
        host, _, outcome = self._restore(document)
        self.assertTrue(outcome[0], outcome)
        self.assertEqual(host._v2_trace_session_id, "legacy-id")
        self.assertEqual(host._v2_trace_started_at, 49_100.0)
        self.assertIs(host._v2_intent, _Intent.NORMAL)
        self.assertIs(host._v2_condition_before, _Condition.UNKNOWN)

    def test_hostile_battery_id_stringification_raises_before_any_mutation(self):
        document = _valid_document(v2_battery_id=_BrokenString())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text("{}", encoding="utf-8")
            host = _host()
            before = dict(host.__dict__)
            with patch("runtime.charge.persistence.json.loads", return_value=document):
                with patch("runtime.charge.persistence.time.time", return_value=time.time()):
                    with self.assertRaisesRegex(RuntimeError, "string conversion exploded"):
                        restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))
            self.assertEqual(host.__dict__, before)

    def test_host_intent_type_conversion_failure_is_preapply(self):
        host = _host()
        host._v2_intent = _FailingIntent("initial")
        document = _valid_document(v2_intent="normal")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            import json
            path.write_text(json.dumps(document), encoding="utf-8")
            before = dict(host.__dict__)
            with patch("runtime.charge.persistence.time.time", return_value=50_000.0):
                with self.assertRaisesRegex(RuntimeError, "intent conversion exploded"):
                    restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))
            self.assertEqual(host.__dict__, before)


if __name__ == "__main__":
    unittest.main()
