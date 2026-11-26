import ast
import inspect
from pathlib import Path
import unittest
from types import SimpleNamespace

from runtime.charge.programs.manual import manual_stop_threshold_reason


_FIELDS = (
    "max_active_seconds",
    "voltage_ge_v",
    "voltage_le_v",
    "current_ge_a",
    "current_le_a",
)


def stop(**overrides):
    values = {name: None for name in _FIELDS}
    values.update(overrides)
    return SimpleNamespace(**values)


class ManualStopThresholdPolicyTests(unittest.TestCase):
    def test_each_threshold_inclusive_boundary(self):
        cases = (
            (stop(max_active_seconds=60), 60, 12.0, 0.0, "manual_time_limit"),
            (stop(voltage_ge_v=14.4), 0, 14.4, 0.0, "manual_voltage_ge"),
            (stop(voltage_le_v=12.0), 0, 12.0, 0.0, "manual_voltage_le"),
            (stop(current_ge_a=2.0), 0, 12.0, 2.0, "manual_current_ge"),
            (stop(current_le_a=0.5), 0, 12.0, 0.5, "manual_current_le"),
        )
        for conditions, elapsed, voltage, current, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    manual_stop_threshold_reason(
                        conditions,
                        active_elapsed_s=elapsed,
                        voltage=voltage,
                        current=current,
                    ),
                    expected,
                )

    def test_original_priority_when_multiple_thresholds_match(self):
        conditions = stop(
            max_active_seconds=10,
            voltage_ge_v=13.0,
            voltage_le_v=15.0,
            current_ge_a=1.0,
            current_le_a=3.0,
        )
        self.assertEqual(
            manual_stop_threshold_reason(
                conditions, active_elapsed_s=10, voltage=14.0, current=2.0
            ),
            "manual_time_limit",
        )
        conditions = stop(voltage_ge_v=13.0, voltage_le_v=15.0)
        self.assertEqual(
            manual_stop_threshold_reason(
                conditions, active_elapsed_s=0, voltage=14.0, current=0.0
            ),
            "manual_voltage_ge",
        )
        conditions = stop(current_ge_a=1.0, current_le_a=3.0)
        self.assertEqual(
            manual_stop_threshold_reason(
                conditions, active_elapsed_s=0, voltage=0.0, current=2.0
            ),
            "manual_current_ge",
        )

    def test_disabled_thresholds_and_no_match_return_none(self):
        self.assertIsNone(
            manual_stop_threshold_reason(
                stop(), active_elapsed_s=0, voltage=12.0, current=0.0
            )
        )
        self.assertIsNone(
            manual_stop_threshold_reason(
                stop(voltage_ge_v=14.0, voltage_le_v=10.0),
                active_elapsed_s=0,
                voltage=12.0,
                current=1.0,
            )
        )

    def test_result_is_stateless_across_calls(self):
        conditions = stop(voltage_ge_v=14.0)
        kwargs = dict(active_elapsed_s=0, voltage=14.0, current=0.0)
        self.assertEqual(manual_stop_threshold_reason(conditions, **kwargs), "manual_voltage_ge")
        self.assertIsNone(
            manual_stop_threshold_reason(
                conditions, active_elapsed_s=0, voltage=13.9, current=0.0
            )
        )
        self.assertEqual(manual_stop_threshold_reason(conditions, **kwargs), "manual_voltage_ge")

    def test_compatibility_method_remains_and_delegates(self):
        source = Path(inspect.getsourcefile(manual_stop_threshold_reason)).resolve()
        manual_mode = source.parents[3] / "manual_mode.py"
        tree = ast.parse(manual_mode.read_text(encoding="utf-8"))
        session_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ManualSessionManager"
        )
        method = next(
            node for node in session_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "_threshold_reason"
        )
        self.assertEqual(
            [arg.arg for arg in method.args.args], ["self", "voltage", "current"]
        )
        self.assertIsInstance(method.body[0], ast.Assert)
        self.assertIsInstance(method.body[1], ast.Return)
        call = method.body[1].value
        self.assertIsInstance(call, ast.Call)
        self.assertIsInstance(call.func, ast.Name)
        self.assertEqual(call.func.id, "manual_stop_threshold_reason")
        self.assertEqual(len(call.args), 1)
        self.assertEqual(ast.unparse(call.args[0]), "self.request.stop")
        self.assertEqual(
            {keyword.arg for keyword in call.keywords},
            {"active_elapsed_s", "voltage", "current"},
        )


if __name__ == "__main__":
    unittest.main()
