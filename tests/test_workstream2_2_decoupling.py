import ast
import unittest
from pathlib import Path

from application.actuator_reachability import actuator_bypasses, actuator_reachability
from application.configuration_decision_registry import unresolved_configuration_decisions
from application.configuration_model import default_configuration_authority
from application.lifecycle_inventory import lifecycle_inventory
from application.safety_boundary import SafetySignal, SafetySignalKind
from application.safety_ownership import SafetyOwnershipCoordinator


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "RD6018_EXECUTION_SAFETY_RUNTIME_DECOUPLING_REPORT.md"


class Workstream22Tests(unittest.TestCase):
    def test_actuator_graph_covers_operations_and_special_paths(self):
        records = actuator_reachability()
        operations = {item.operation for item in records}
        self.assertTrue({"OUTPUT_ON", "OUTPUT_OFF", "SET_VOLTAGE", "SET_CURRENT", "STOP", "EMERGENCY_OFF", "CONTAINMENT"} <= operations)
        self.assertTrue(all(not item.dispatch_enabled for item in records))
        self.assertTrue(actuator_bypasses())  # legacy V2 paths remain explicit, not silently hidden

    def test_safety_has_one_logical_decision_owner(self):
        coordinator = SafetyOwnershipCoordinator()
        observation = coordinator.evaluate(SafetySignal(SafetySignalKind.WATCHDOG, "test", False, "timeout"), trace_id="ws22")
        self.assertEqual("Safety Decision Authority", observation.decision.owner)
        self.assertIsNotNone(observation.containment)
        self.assertFalse(observation.dispatch_enabled)
        self.assertEqual((), coordinator.ownership_conflicts())

    def test_configuration_registry_is_complete_for_current_model(self):
        authority = default_configuration_authority()
        self.assertTrue(authority.keys())
        for key in authority.keys():
            parameter = authority.get(key)
            self.assertTrue(parameter.owner and parameter.source and parameter.description)
            self.assertTrue(callable(parameter.validator))
        self.assertTrue(any(item.status.value == "UNRESOLVED" for item in unresolved_configuration_decisions()))

    def test_lifecycle_inventory_keeps_v2_risk_explicit(self):
        entries = {item.module: item for item in lifecycle_inventory()}
        self.assertTrue(entries["runtime/v2_runtime.py"].import_side_effects)
        self.assertEqual("ApplicationComposition", entries["application/composition_lifecycle.py"].lifecycle_owner)
        self.assertTrue(all(not item.runtime_start for item in entries.values() if item.status in {"CONTRACT_ONLY", "SHADOW_ONLY"}))

    def test_application_modules_do_not_create_runtime_or_physical_side_effects(self):
        for path in (ROOT / "application").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual((getattr(node.func.value, "id", ""), node.func.attr), ("asyncio", "run"), path.name)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("HassClient(", text, path.name)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            self.assertFalse(any("esphome" in item.lower() for item in imports), path.name)

    def test_report_requires_repeat_audit_and_actual_status(self):
        text = REPORT.read_text(encoding="utf-8")
        for marker in ("B3", "B4", "B5", "B6", "WORKSTREAM 1", "ARCHITECTURE PASS"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
