"""The logger delegates its guarded OFF reason read to the canonical owner."""

import ast
import unittest
from pathlib import Path


class OperatorOffLoggerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py").read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(cls.source)
        cls.logger = next(
            node for node in ast.walk(cls.tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "data_logger"
        )

    def test_one_evaluation_inside_original_output_and_armed_guard(self):
        calls = [node for node in ast.walk(self.logger)
                 if isinstance(node, ast.Call)
                 and ast.unparse(node.func) == "_operator_off_conditions.evaluate_reason"]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        guard = next(node for node in ast.walk(self.logger)
                     if isinstance(node, ast.If) and node.test is not None
                     and ast.unparse(node.test) == "output_on and _has_manual_off_condition()"
                     and call in list(ast.walk(node)))
        body = [ast.unparse(statement) for statement in guard.body]
        self.assertEqual(body[0], "now_ts = time.time()")
        self.assertEqual(body[1], "off_reason = _operator_off_conditions.evaluate_reason(battery_v, i, now_s=now_ts, reach_eps=OFF_REACH_EPS)")
        self.assertTrue(body[2].startswith("if off_reason:"))
        self.assertEqual([ast.unparse(arg) for arg in call.args], ["battery_v", "i"])
        self.assertEqual({kw.arg: ast.unparse(kw.value) for kw in call.keywords},
                         {"now_s": "now_ts", "reach_eps": "OFF_REACH_EPS"})

    def test_logger_side_effect_order_and_owner_lock_remain_in_cycle(self):
        source = self.source
        cycle = source[source.index("if output_on and _has_manual_off_condition():"):]
        expected = [
            "off_reason = _operator_off_conditions.evaluate_reason(",
            "log_event(charge_controller.current_stage, battery_v, i, t, ah, f\"MANUAL_OFF_{off_reason[:30]}\")",
            "_charge_notify(f\"⏹ Выключено по условию: {off_reason}\")",
            "await _hard_stop_charge()",
            "_clear_manual_off()",
            "await add_record(battery_v, i, p, t)",
            "if _operator_pause_active():",
        ]
        positions = [cycle.index(item) for item in expected]
        self.assertEqual(positions, sorted(positions))
        protection = source.index("protection_decision = evaluate_live_protection(")
        self.assertLess(protection, source.index("if output_on and _has_manual_off_condition():"))
        self.assertIn("async with _runtime_execution_port()._guard_owner_lock:", source)

    def test_evaluator_has_no_clock_or_side_effect_dependencies(self):
        owner_path = Path(__file__).resolve().parents[1] / "runtime" / "operator" / "off_conditions.py"
        owner_tree = ast.parse(owner_path.read_text(encoding="utf-8"))
        owner_class = next(node for node in owner_tree.body
                           if isinstance(node, ast.ClassDef) and node.name == "OperatorOffConditions")
        method = next(node for node in owner_class.body
                      if isinstance(node, ast.FunctionDef) and node.name == "evaluate_reason")
        calls = {ast.unparse(node.func) for node in ast.walk(method) if isinstance(node, ast.Call)}
        self.assertNotIn("time.time", calls)
        self.assertFalse(any(name.endswith((".save", ".clear", ".log", ".warning", ".info")) for name in calls))
        self.assertNotIn("_hard_stop_charge", calls)


if __name__ == "__main__":
    unittest.main()
