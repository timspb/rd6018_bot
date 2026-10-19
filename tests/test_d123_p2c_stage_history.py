import ast
from pathlib import Path
import unittest

from charge_controller import ManagedChargeController


ROOT = Path(__file__).resolve().parents[1]


class StageHistoryConvergenceTests(unittest.TestCase):
    def test_setter_records_one_edge_and_resets_stage_metrics_once(self):
        controller = ManagedChargeController(object())
        controller._stage_tracking_enabled = True
        controller._last_transition_reason = "guard accepted"
        controller._stage_start_voltage = 13.2
        controller.current_stage = controller.STAGE_MAIN
        self.assertEqual(len(controller._stage_history), 1)
        self.assertEqual(controller._stage_history[0]["from"], controller.STAGE_IDLE)
        self.assertEqual(controller._stage_history[0]["to"], controller.STAGE_MAIN)
        self.assertEqual(controller._stage_history[0]["reason"], "guard accepted")
        self.assertEqual(controller._stage_start_voltage, 0.0)
        controller.current_stage = controller.STAGE_MAIN
        self.assertEqual(len(controller._stage_history), 1)
        controller.current_stage = controller.STAGE_DESULFATION
        self.assertEqual(len(controller._stage_history), 2)
        self.assertEqual(controller.previous_stage, controller.STAGE_MAIN)

    def test_restore_preserves_serialized_history_contract(self):
        controller = ManagedChargeController(object())
        from runtime.charge.session import restore_stage_history

        restore_stage_history(controller, None, "resume", [{
            "from": "MAIN", "to": "DESULFATION", "reason": "guard", "ts": 123.5,
        }], now=999.0)
        self.assertEqual(controller.previous_stage, "MAIN")
        self.assertEqual(controller._last_transition_reason, "resume")
        self.assertEqual(list(controller._stage_history), [{
            "from": "MAIN", "to": "DESULFATION", "reason": "guard", "ts": 123.5,
        }])

    def test_transition_and_restore_bodies_have_one_modular_owner(self):
        tree = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "ManagedChargeController")
        setter = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "current_stage"
                      and any(isinstance(dec, ast.Attribute) and dec.attr == "setter"
                              for dec in node.decorator_list))
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "set_current_stage" for n in ast.walk(setter)), 1)
        source = (ROOT / "runtime/charge/persistence.py").read_text(encoding="utf-8")
        self.assertIn("restore_stage_history(\n", source)
        self.assertNotIn('host._stage_history.append(\n', source)


if __name__ == "__main__":
    unittest.main()
