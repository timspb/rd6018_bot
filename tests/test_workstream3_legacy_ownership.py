import ast
import unittest
from pathlib import Path

from application.actuator_ownership_map import canonical_actuator_paths, direct_bypasses
from application.configuration_registry import canonical_configuration_registry, configuration_drift_entries
from application.safety_boundary import SAFETY_DECISION_OWNER
from application.safety_ownership_map import active_execution_writers, safety_ownership_map


ROOT = Path(__file__).resolve().parents[1]


class Workstream3Tests(unittest.TestCase):
    def test_legacy_domain_import_isolated_to_named_adapter(self):
        for path in (ROOT / "application").glob("*.py"):
            if path.name == "legacy_domain_adapter.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "runtime.charge", path.name)
                    self.assertNotEqual(node.module, "runtime.charge.strategy", path.name)
        adapter = (ROOT / "application" / "legacy_domain_adapter.py").read_text(encoding="utf-8")
        self.assertIn("from runtime.charge", adapter)

    def test_actuator_map_is_canonical_and_explicit(self):
        paths = canonical_actuator_paths()
        self.assertGreaterEqual(len(paths), 25)
        self.assertTrue({"OUTPUT_ON", "OUTPUT_OFF", "SET_VOLTAGE", "SET_CURRENT", "STOP", "EMERGENCY_OFF", "CONTAINMENT"} <= {p.operation for p in paths})
        self.assertTrue(all(p.owner and p.source and p.path and p.adapter and p.physical_target and p.migration_state for p in paths))
        self.assertTrue(direct_bypasses())

    def test_configuration_registry_has_provenance_and_explicit_drift(self):
        entries = canonical_configuration_registry()
        self.assertGreaterEqual(len(entries), 20)
        self.assertTrue(all(entry.owner and entry.section and entry.value_type and entry.provenance for entry in entries))
        self.assertTrue(configuration_drift_entries())
        self.assertTrue(any(entry.migration_status == "UNRESOLVED" for entry in entries))

    def test_safety_map_has_one_logical_decision_owner_and_multiple_legacy_writers(self):
        records = safety_ownership_map()
        self.assertEqual({SAFETY_DECISION_OWNER}, {record.decision_owner for record in records})
        self.assertGreater(len(active_execution_writers()), 1)
        self.assertTrue(all(record.execution_owner and record.physical_boundary for record in records))

    def test_application_modules_have_no_runtime_start_or_physical_client_creation(self):
        for path in (ROOT / "application").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual((getattr(node.func.value, "id", ""), node.func.attr), ("asyncio", "run"), path.name)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("HassClient(", text, path.name)


if __name__ == "__main__":
    unittest.main()
