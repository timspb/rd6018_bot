import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DiagnosticSnapshotOwnershipTests(unittest.TestCase):
    def test_bank_fault_snapshot_has_no_controller_facade(self):
        controller = ast.parse((ROOT / "charge_controller.py").read_text(encoding="utf-8"))
        managed = next(node for node in controller.body if isinstance(node, ast.ClassDef)
                       and node.name == "ManagedChargeController")
        names = {node.name for node in managed.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("_bank_fault_risk_snapshot", names)

    def test_snapshot_projection_is_owned_by_runtime_diagnostics_and_application(self):
        diagnostics = ast.parse((ROOT / "runtime/charge/diagnostics.py").read_text(encoding="utf-8"))
        self.assertIn("diagnostic_assessment_snapshot", {
            node.name for node in diagnostics.body if isinstance(node, ast.FunctionDef)
        })
        application = ast.parse((ROOT / "application/charge_stage_tick.py").read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(node, ast.ImportFrom)
                            and node.module == "runtime.charge.diagnostics"
                            and any(alias.name == "diagnostic_assessment_snapshot" for alias in node.names)
                            for node in application.body))
        controller = ast.parse((ROOT / "diagnostic_controller.py").read_text(encoding="utf-8"))
        self.assertNotIn("diagnostic_snapshot", {
            node.name for node in ast.walk(controller) if isinstance(node, ast.FunctionDef)
        })


if __name__ == "__main__":
    unittest.main()
