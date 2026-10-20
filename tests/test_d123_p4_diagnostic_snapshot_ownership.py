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

    def test_diagnostic_controller_calls_canonical_diagnostic_owner(self):
        tree = ast.parse((ROOT / "diagnostic_controller.py").read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
                   and node.module == "runtime.charge.diagnostics"]
        self.assertTrue(any(alias.name == "bank_fault_risk_snapshot"
                            for node in imports for alias in node.names))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "bank_fault_risk_snapshot"]
        self.assertEqual(len(calls), 1)
        self.assertNotIn("_bank_fault_risk_snapshot", {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        })


if __name__ == "__main__":
    unittest.main()
