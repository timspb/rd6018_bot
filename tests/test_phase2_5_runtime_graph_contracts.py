"""Static Phase 2.5 reachability contracts; no runtime is imported or executed."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_ROOTS = (
    ROOT / "application",
    ROOT / "runtime" / "application",
    ROOT / "runtime" / "ui",
    ROOT / "telegram",
)
FORBIDDEN_MODULES = ("runtime.physical", "runtime.output.bridge", "physical_test_control")
FORBIDDEN_TYPES = {
    "HassClient",
    "PhysicalExecutionGate",
    "PhysicalBridgeExecutor",
    "OutputExecutor",
    "ChargeController",
}
EXECUTION_TYPES = {
    "ProductionStartExecutionPort",
    "ProductionStartRunner",
    "V2StartTransactionAdapter",
    "V2StartTransactionExecutor",
}


def _files(root: Path):
    if root.exists():
        yield from root.rglob("*.py")


class Phase25RuntimeGraphTests(unittest.TestCase):
    def test_v3_import_graph_has_no_actuator_or_physical_types(self):
        violations = []
        for root in BOUNDARY_ROOTS:
            for path in _files(root):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        names = [alias.name for alias in node.names]
                        if module.startswith(FORBIDDEN_MODULES) or set(names) & FORBIDDEN_TYPES:
                            violations.append(f"{path.relative_to(ROOT)}:{module}")
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith(FORBIDDEN_MODULES):
                                violations.append(f"{path.relative_to(ROOT)}:{alias.name}")
        self.assertEqual(violations, [])

    def test_ui_has_no_execution_owner_construction(self):
        violations = []
        for root in (ROOT / "runtime" / "ui", ROOT / "telegram"):
            for path in _files(root):
                source = path.read_text(encoding="utf-8")
                for type_name in EXECUTION_TYPES:
                    if type_name + "(" in source:
                        violations.append(f"{path.relative_to(ROOT)}:{type_name}")
        self.assertEqual(violations, [])

    def test_execution_composition_is_present_only_at_v2_boundary(self):
        source = (ROOT / "v2_bootstrap.py").read_text(encoding="utf-8")
        for type_name in EXECUTION_TYPES:
            self.assertIn(type_name + "(", source)
        self.assertIn("app._v3_production_start_route", source)

    def test_graph_documents_exist(self):
        for name in (
            "RD6018_RUNTIME_SAFETY_GRAPH.md",
            "RD6018_ACTUATOR_REACHABILITY_MAP.md",
        ):
            self.assertTrue((ROOT / "docs" / name).is_file())


if __name__ == "__main__":
    unittest.main()
