"""Phase 1 architecture contracts.

These tests are static characterization tests. They do not import the
production composition or execute any actuator path.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

V3_BOUNDARY_DIRS = (
    REPO_ROOT / "application",
    REPO_ROOT / "runtime" / "application",
    REPO_ROOT / "runtime" / "ui",
    REPO_ROOT / "telegram",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "runtime.physical",
    "runtime.output.bridge",
    "physical_test_control",
)

FORBIDDEN_IMPORT_NAMES = {
    "HassClient",
    "PhysicalExecutionGate",
    "PhysicalBridgeExecutor",
    "OutputExecutor",
    "ChargeController",
}

ACTUATOR_METHODS = {
    "turn_on",
    "turn_off",
    "set_voltage",
    "set_current",
    "safe_enable_output",
}

EXECUTION_TYPES = {
    "ProductionStartExecutionPort",
    "ProductionStartRunner",
    "V2StartTransactionAdapter",
    "V2StartTransactionExecutor",
}


def _python_files(root: Path):
    if not root.exists():
        return
    yield from root.rglob("*.py")


def _tree(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class Phase1CleanupContractTests(unittest.TestCase):
    def test_v3_and_ui_do_not_import_physical_or_actuator_objects(self):
        violations = []
        for root in V3_BOUNDARY_DIRS:
            for path in _python_files(root):
                tree = _tree(path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        names = [f"{module}.{alias.name}" for alias in node.names]
                    else:
                        continue
                    for name in names:
                        if name.startswith(FORBIDDEN_IMPORT_PREFIXES) or name.rsplit(".", 1)[-1] in FORBIDDEN_IMPORT_NAMES:
                            violations.append(f"{path.relative_to(REPO_ROOT)}:{name}")
        self.assertEqual(violations, [], "V3/UI physical import boundary violated: " + repr(violations))

    def test_v3_and_ui_do_not_call_actuators_directly(self):
        violations = []
        for root in V3_BOUNDARY_DIRS:
            for path in _python_files(root):
                # This is the explicit V2 execution boundary. Its contract is
                # to call the already-owned setter; decision and UI modules
                # remain covered by this scan.
                if path.name in {"manual_execution_boundary.py", "execution_port.py"}:
                    continue
                tree = _tree(path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if node.func.attr in ACTUATOR_METHODS:
                            violations.append(f"{path.relative_to(REPO_ROOT)}:{node.func.attr}")
        self.assertEqual(violations, [], "V3/UI direct actuator call detected: " + repr(violations))

    def test_v2_composition_is_the_production_execution_composition_root(self):
        bootstrap = (REPO_ROOT / "v2_bootstrap.py").read_text(encoding="utf-8")
        for type_name in EXECUTION_TYPES:
            self.assertIn(type_name + "(", bootstrap, f"{type_name} is not composed by v2_bootstrap.py")
        self.assertIn("app._v3_production_start_route", bootstrap)

        # Telegram/UI modules may submit an intent, but must not construct the
        # execution owner themselves.
        violations = []
        for root in (REPO_ROOT / "telegram", REPO_ROOT / "runtime" / "ui"):
            for path in _python_files(root):
                text = path.read_text(encoding="utf-8")
                for type_name in EXECUTION_TYPES:
                    if type_name + "(" in text:
                        violations.append(f"{path.relative_to(REPO_ROOT)}:{type_name}")
        self.assertEqual(violations, [], "UI composition owns execution: " + repr(violations))

    def test_phase1_documents_exist(self):
        for name in (
            "RD6018_OWNERSHIP_MANIFEST.md",
            "RD6018_CONFIGURATION_DRIFT_REPORT.md",
            "RD6018_LEGACY_ROUTE_INVENTORY.md",
            "RD6018_PHASE_1_CLEANUP.md",
        ):
            self.assertTrue((REPO_ROOT / "docs" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
