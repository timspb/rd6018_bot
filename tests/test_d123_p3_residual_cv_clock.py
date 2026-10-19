import ast
import unittest
from pathlib import Path

from runtime.charge.runtime.residual_observation import update_residual_cv_clock


ROOT = Path(__file__).resolve().parents[1]


class ResidualCvClockOwnershipTests(unittest.TestCase):
    def test_first_cv_is_retained_and_cc_resets_clock(self):
        class Host:
            _cv_since = None

        host = Host()
        update_residual_cv_clock(host, is_cv=True, timestamp_s=10.0)
        update_residual_cv_clock(host, is_cv=True, timestamp_s=20.0)
        self.assertEqual(host._cv_since, 10.0)
        update_residual_cv_clock(host, is_cv=False, timestamp_s=30.0)
        self.assertIsNone(host._cv_since)

    def test_residual_scaffold_calls_owner_once_without_inline_mutation(self):
        source = (ROOT / "runtime/charge/runtime/residual_scaffold.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "update_residual_cv_clock"]
        self.assertEqual(len(calls), 1)
        self.assertNotIn("host._cv_since =", source)

    def test_owner_has_no_physical_writer_boundary(self):
        source = (ROOT / "runtime/charge/runtime/residual_observation.py").read_text(encoding="utf-8")
        for forbidden in ("execution_port", "set_voltage", "set_current", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, source)
