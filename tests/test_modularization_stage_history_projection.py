"""Pure projection contract for restored stage history."""

import ast
import inspect
import subprocess
import sys
import unittest
from collections import deque
from unittest.mock import patch

from runtime.charge import session
from runtime.charge.session import (
    normalize_restored_stage_history,
    restore_stage_history,
)


class _Host:
    def __init__(self, maxlen=4):
        self.previous_stage = "old-stage"
        self._last_transition_reason = "old-reason"
        self._stage_history = deque([{"from": "old", "to": "item"}], maxlen=maxlen)


class StageHistoryProjectionTests(unittest.TestCase):
    def test_pure_normalizer_preserves_legacy_rules_and_tail_before_filtering(self):
        source = [
            {"from": "ignored", "to": "entry", "ts": 1},
            "invalid",
            {"from": " A ", "to": " B ", "reason": " why ", "ts": "bad"},
            {"from": " ", "to": " ", "ts": 7},
            {"from": "C", "to": "D", "reason": " next ", "ts": 3},
        ]
        result = normalize_restored_stage_history(None, " r ", source, now=99, maxlen=4)
        previous, reason, history = result
        self.assertEqual(previous, "C")
        self.assertEqual(reason, " r ")
        self.assertIsInstance(history, tuple)
        self.assertEqual(history, (
            {"from": "A", "to": "B", "reason": "why", "ts": 99.0},
            {"from": "C", "to": "D", "reason": "next", "ts": 3.0},
        ))
        self.assertIsNot(history[0], source[2])
        self.assertEqual(source[2]["from"], " A ")
        # Selection occurs before invalid-entry filtering: only the last two
        # selected values remain, and the invalid one is not backfilled.
        _, _, selected = normalize_restored_stage_history(
            "saved", "", [{"from": "A"}, {"from": "B"}, "bad"], now=1, maxlen=2
        )
        self.assertEqual(selected, ({"from": "B", "to": "", "reason": "", "ts": 1.0},))

    def test_roots_bad_timestamps_falsey_stage_and_zero_maxlen(self):
        for root in ("bad", {"bad": "shape"}, None, 12):
            with self.subTest(root=root):
                self.assertEqual(
                    normalize_restored_stage_history("saved", None, root, now=8, maxlen=3),
                    ("saved", "", ()),
                )
        for bad_timestamp in ("bad", object(), 10**10000):
            with self.subTest(ts=type(bad_timestamp).__name__):
                _, _, items = normalize_restored_stage_history(
                    False, 0, [{"from": " P ", "to": "Q", "ts": bad_timestamp}], now=8, maxlen=3
                )
                self.assertEqual(items[0]["ts"], 8.0)
                self.assertEqual(items[0]["from"], "P")
        self.assertEqual(
            normalize_restored_stage_history(None, "", [{"from": "A", "to": "B"}], now=1, maxlen=0)[2],
            ({"from": "A", "to": "B", "reason": "", "ts": 1.0},),
        )

    def test_legacy_restorer_only_applies_pure_result_to_host(self):
        host = _Host(maxlen=2)
        raw = [{"from": " A ", "to": "B", "ts": 2}, {"from": "B", "to": "C", "ts": 3}]
        expected = normalize_restored_stage_history(None, "reason", raw, now=9, maxlen=2)
        with patch("runtime.charge.session.normalize_restored_stage_history", return_value=expected) as pure:
            restore_stage_history(host, None, "reason", raw, now=9)
        pure.assert_called_once_with(None, "reason", raw, now=9, maxlen=2)
        self.assertEqual((host.previous_stage, host._last_transition_reason), expected[:2])
        self.assertEqual(tuple(host._stage_history), expected[2])

    def test_projection_function_has_no_host_or_io_references(self):
        source = inspect.getsource(normalize_restored_stage_history)
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertNotIn("host", names)
        self.assertFalse(names & {"open", "Path", "requests", "socket"})
        self.assertFalse(attrs & {"read", "write", "connect"})

    def test_module_import_has_no_runtime_io_or_clock_side_effect(self):
        # Reloading the shared module replaces dataclass identities for later
        # tests in this pytest process. Probe import-time behavior in isolation.
        script = (
            "from unittest.mock import patch\n"
            "with patch('builtins.open', side_effect=AssertionError('unexpected I/O')), "
            "patch('time.time', side_effect=AssertionError('unexpected clock read')):\n"
            "    import runtime.charge.session\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=__import__("pathlib").Path(__file__).resolve().parents[1],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
