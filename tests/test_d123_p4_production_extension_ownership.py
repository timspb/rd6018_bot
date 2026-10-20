import ast
import pathlib
import unittest

from application.production_session_extensions import operatorize_notification
from production_controller import create_production_charge_host
from charge_controller import ManagedChargeController


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProductionExtensionOwnershipTests(unittest.TestCase):
    def test_application_extensions_are_not_controller_facades(self):
        removed = {
            "_apply_continuous_tail_hold",
            "_capture_cooling_pause",
            "_resume_cooling_pause",
            "_restore_runtime_signal_snapshot",
            "_runtime_signal_snapshot",
            "_operatorize_notification",
            "_save_session",
            "_restore_finish_state",
            "_valid_finish_evidence",
            "_restore_runtime_signal_state",
        }
        self.assertTrue({"_apply_continuous_tail_hold", "_save_session"}.issubset(
            ManagedChargeController.__dict__
        ))
        for source_name in ("production_controller.py", "auto_strategy.py", "diagnostic_controller.py"):
            source = ast.parse((ROOT / source_name).read_text())
            for cls in (node for node in source.body if isinstance(node, ast.ClassDef)):
                methods = {
                    node.name for node in cls.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                self.assertTrue(removed.isdisjoint(methods), f"{source_name}:{cls.name}")
        tree = ast.parse((ROOT / "application/production_session_extensions.py").read_text())
        self.assertFalse(any(isinstance(node, ast.ClassDef) for node in tree.body))
        functions = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue({
            "apply_continuous_tail_hold", "capture_cooling_pause", "resume_cooling_pause",
            "restore_runtime_signal_snapshot", "operatorize_notification",
            "runtime_signal_snapshot",
            "session_document_extensions", "restore_finish_state",
            "valid_finish_evidence", "restore_runtime_signal_state",
        }.issubset(functions))

    def test_production_extension_owner_has_no_physical_writer(self):
        tree = ast.parse((ROOT / "application/production_session_extensions.py").read_text())
        forbidden = {
            "safe_enable_output", "turn_on", "set_voltage", "set_current", "set_ovp", "set_ocp",
            "save_session", "atomic_session_write", "open",
        }
        calls = {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue(forbidden.isdisjoint(calls))
        self.assertFalse(any(
            isinstance(node, ast.Import) and any(alias.name == "os" for alias in node.names)
            for node in tree.body
        ))
        for source_name in ("production_controller.py", "auto_strategy.py", "diagnostic_controller.py"):
            controller_tree = ast.parse((ROOT / source_name).read_text())
            for cls in (node for node in controller_tree.body if isinstance(node, ast.ClassDef)):
                methods = {
                    node.name for node in cls.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                calls = {
                    node.func.attr for node in ast.walk(cls)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                }
                self.assertTrue(forbidden.isdisjoint(methods | calls), f"{source_name}:{cls.name}")

    def test_operator_notification_projection_preserves_known_wording(self):
        self.assertEqual(
            operatorize_notification("main_tail_hold_complete_normal_charge"),
            "Хвост основного заряда стабилен; основной заряд завершён.",
        )
        self.assertEqual(
            operatorize_notification("<b>🎯 V2 Delta подтверждена</b>"),
            "<b>🎯 Delta подтверждена</b>",
        )


if __name__ == "__main__":
    unittest.main()
