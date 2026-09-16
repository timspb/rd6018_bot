"""Shadow-only actuator intent mapping tests."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from application.actuator_intent import ActuatorOperation
from application.actuator_intent_mapping import (
    known_actuator_paths,
    observe_actuator_path,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase41ActuatorMappingTests(unittest.TestCase):
    def test_every_production_reachable_path_is_mapped(self):
        paths = known_actuator_paths()
        self.assertGreaterEqual(len(paths), 10)
        ids = [path.path_id for path in paths]
        self.assertEqual(len(ids), len(set(ids)))
        for path in paths:
            intent = observe_actuator_path(path.path_id, trace_id="trace-test")
            self.assertEqual(intent.requested_operation, path.current_operation)
            self.assertEqual(intent.source, path.caller)
            self.assertEqual(intent.owner, path.owner)
            self.assertEqual(intent.reason, path.reason)
            self.assertEqual(intent.target, path.target)

    def test_unknown_operation_or_path_is_rejected(self):
        with self.assertRaises(KeyError):
            observe_actuator_path("unknown-actuator-path", trace_id="trace-test")
        with self.assertRaises(ValueError):
            ActuatorOperation("unknown-operation")

    def test_all_operations_are_represented(self):
        self.assertEqual(
            {path.current_operation for path in known_actuator_paths()},
            set(ActuatorOperation),
        )

    def test_mapping_has_no_physical_side_effects(self):
        path = ROOT / "application" / "actuator_intent_mapping.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        self.assertTrue(all(not item.startswith(("hass_api", "runtime.physical", "safe_output")) for item in imports))
        self.assertTrue(calls.isdisjoint({"turn_on", "turn_off", "set_voltage", "set_current", "start", "stop"}))

    def test_ui_cannot_create_intents_or_execution_owners(self):
        violations = []
        for root in (ROOT / "telegram", ROOT / "runtime" / "ui"):
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                for name in ("ActuatorIntent", "ExistingActuatorRequest", "ProductionStartRunner", "HassClient"):
                    if name + "(" in source:
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual(violations, [])

    def test_mapping_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_ACTUATOR_INTENT_MAPPING.md").is_file())


if __name__ == "__main__":
    unittest.main()
