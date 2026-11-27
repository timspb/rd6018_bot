"""Fake-only fault injection for persisted stage history and trace restore."""

import json
import tempfile
import unittest
import uuid
from collections import deque
from enum import Enum
from pathlib import Path
from unittest.mock import patch

from runtime.charge.persistence import restore_session
from runtime.charge.session import (
    apply_trace_identity,
    restore_stage_history,
    restore_trace_identity,
)
from tests.test_modularization_auto_restore_atomic_admission import (
    _Host,
    _valid_document,
)


class _TraceIntent(str, Enum):
    NORMAL = "normal"


class _TraceCondition(str, Enum):
    UNKNOWN = "unknown"


class _TraceHost:
    total_start_time = 1234.5
    battery_type = "Ca/Ca"
    ah_capacity = 60
    host_configuration = None
    _v2_intent = _TraceIntent.NORMAL
    _v2_condition_before = _TraceCondition.UNKNOWN
    _v2_battery_id = "existing-battery"


class _BrokenString:
    def __str__(self):
        raise RuntimeError("string conversion exploded")


class RestoreHistoryTraceContract(unittest.TestCase):
    def test_history_normalizes_filters_bounds_and_falls_back_timestamp(self):
        host = _Host()
        host._stage_history = deque(maxlen=3)
        restore_stage_history(
            host,
            None,
            "  transition  ",
            [
                {"from": " A ", "to": " B ", "reason": " why ", "ts": "bad"},
                "malformed entry",
                {"from": "B", "to": "C", "reason": " next ", "ts": 2},
                {"from": "C", "to": "D", "reason": "last", "ts": 3},
                {"from": "D", "to": "E", "reason": "tail", "ts": 4},
            ],
            now=99.0,
        )
        self.assertEqual(host._last_transition_reason, "  transition  ")
        self.assertEqual(list(host._stage_history), [
            {"from": "B", "to": "C", "reason": "next", "ts": 2.0},
            {"from": "C", "to": "D", "reason": "last", "ts": 3.0},
            {"from": "D", "to": "E", "reason": "tail", "ts": 4.0},
        ])
        self.assertEqual(host.previous_stage, "D")
        restore_stage_history(
            host, None, "", [{"from": "A", "to": "B", "ts": "bad"}], now=99.0
        )
        self.assertEqual(host._stage_history[-1]["ts"], 99.0)
        self.assertEqual(host.previous_stage, "A")

    def test_history_malformed_roots_and_maxlen_edges(self):
        for root in (["bad"], "bad", {"bad": "shape"}, None):
            with self.subTest(root=root):
                host = _Host()
                restore_stage_history(host, "saved-previous", "saved-reason", root, now=1)
                self.assertEqual(list(host._stage_history), [])
                self.assertEqual(host.previous_stage, "saved-previous")
                self.assertEqual(host._last_transition_reason, "saved-reason")

        zero = _Host()
        zero._stage_history = deque(maxlen=0)
        restore_stage_history(zero, None, "", [{"from": "A", "to": "B"}], now=1)
        self.assertEqual(list(zero._stage_history), [])
        self.assertIsNone(zero.previous_stage)

        invalid = _Host()
        invalid._stage_history = deque()
        with self.assertRaises(TypeError):
            restore_stage_history(invalid, None, "", [{"from": "A", "to": "B"}], now=1)

    def test_trace_legacy_id_timestamp_and_enum_fallbacks(self):
        host = _TraceHost()
        document = {
            "profile": "Ca/Ca", "ah_limit": 60, "saved_at": 7,
            "v2_trace_started_at": "malformed", "v2_intent": "not-an-intent",
            "v2_condition_before": "not-a-condition",
        }
        with patch("runtime.charge.session.time.time", return_value=4321.0):
            snapshot = restore_trace_identity(host, document)
        expected = uuid.uuid5(
            uuid.NAMESPACE_URL, "rd6018-recovery:Ca/Ca|60|1234.500000|7"
        ).hex
        self.assertEqual(snapshot.session_id, expected)
        self.assertEqual(snapshot.started_at, 1234.5)
        self.assertEqual(snapshot.battery_id, "existing-battery")
        self.assertEqual(snapshot.intent, "normal")
        self.assertEqual(snapshot.condition_before, "unknown")
        apply_trace_identity(host, snapshot)
        self.assertEqual(host._v2_trace_session_id, expected)
        self.assertIs(host._v2_intent, _TraceIntent.NORMAL)
        self.assertIs(host._v2_condition_before, _TraceCondition.UNKNOWN)

    def test_trace_identity_exotic_battery_id_can_raise(self):
        with self.assertRaisesRegex(RuntimeError, "string conversion exploded"):
            restore_trace_identity(_TraceHost(), {"v2_battery_id": _BrokenString()})

    def test_restore_exotic_trace_value_raises_before_controller_mutation(self):
        document = _valid_document(v2_battery_id=_BrokenString())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text("{}", encoding="utf-8")
            host = _Host()
            before = dict(host.__dict__)
            with patch("runtime.charge.persistence.json.loads", return_value=document):
                with self.assertRaisesRegex(RuntimeError, "string conversion exploded"):
                    restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))

        changed = {
            key for key in set(before) | set(host.__dict__)
            if before.get(key, object()) != host.__dict__.get(key, object())
        }
        self.assertEqual(changed, set(), "trace projection failure must precede controller mutation")

    def test_restore_accepts_malformed_nested_history_and_trace_with_mutations(self):
        doc = _valid_document(
            stage_history={"unexpected": "object"}, previous_stage=None,
            v2_trace_started_at="malformed", v2_trace_session_id="",
            v2_battery_id={"json": "object"}, v2_intent="invalid-intent",
            v2_condition_before=["invalid-condition"],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            host = _Host()
            host._v2_intent = _TraceIntent.NORMAL
            host._v2_condition_before = _TraceCondition.UNKNOWN
            outcome = restore_session(host, 12.5, 0.0, 0.0, session_file=str(path))

        self.assertTrue(outcome[0], outcome)
        self.assertEqual(host.current_stage, "Main Charge")
        self.assertEqual(list(host._stage_history), [])
        self.assertIsNone(host.previous_stage)
        self.assertTrue(host._v2_trace_session_id)
        self.assertEqual(host._v2_battery_id, "{'json': 'object'}")
        self.assertIs(host._v2_intent, _TraceIntent.NORMAL)
        self.assertIs(host._v2_condition_before, _TraceCondition.UNKNOWN)
        self.assertTrue(host._session_restore_snapshot)


if __name__ == "__main__":
    unittest.main()
