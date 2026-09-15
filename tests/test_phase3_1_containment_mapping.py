"""Static/side-effect-free tests for Phase 3.1 containment mapping."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from application.containment_mapping import (
    known_containment_mappings,
    observe_containment,
)
from application.containment_result import ContainmentVerificationState


ROOT = Path(__file__).resolve().parents[1]


class Phase31ContainmentMappingTests(unittest.TestCase):
    def test_every_known_containment_path_has_mapping(self):
        mappings = known_containment_mappings()
        self.assertGreaterEqual(len(mappings), 10)
        ids = [mapping.path_id for mapping in mappings]
        self.assertEqual(len(ids), len(set(ids)))
        for mapping in mappings:
            result = observe_containment(mapping.path_id, trace_id="trace-test")
            self.assertEqual(result.source, mapping.source)
            self.assertEqual(result.trigger, mapping.trigger)
            self.assertEqual(result.requested_action, mapping.requested_action)
            self.assertEqual(result.physical_owner, mapping.physical_owner)
            self.assertEqual(result.verification_state, mapping.verification_state)

    def test_unknown_path_is_rejected_without_side_effect(self):
        with self.assertRaises(KeyError):
            observe_containment("not-a-real-path", trace_id="trace-test")

    def test_mapping_module_has_no_physical_calls_or_runtime_wiring(self):
        path = ROOT / "application" / "containment_mapping.py"
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

    def test_mapping_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_CONTAINMENT_MAPPING.md").is_file())


if __name__ == "__main__":
    unittest.main()
