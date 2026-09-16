"""Shadow-only tests for containment observation collection."""

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from application.containment_mapping import known_containment_mappings
from application.containment_observation import (
    ContainmentObservationCollector,
    ContainmentObservationRecord,
)
from application.containment_result import ContainmentVerificationState


ROOT = Path(__file__).resolve().parents[1]


class Phase32ContainmentObservationTests(unittest.TestCase):
    def test_every_known_path_generates_observation(self):
        collector = ContainmentObservationCollector()
        mappings = known_containment_mappings()
        self.assertTrue(mappings)
        for mapping in mappings:
            record = collector.observe(
                mapping.path_id,
                trace_id="trace-test",
                session_id="session-test",
                timestamp=123.0,
            )
            self.assertIsInstance(record, ContainmentObservationRecord)
            self.assertEqual(record.source, mapping.source)
            self.assertEqual(record.trigger, mapping.trigger)
            self.assertEqual(record.requested_action, mapping.requested_action)
            self.assertEqual(record.verification_state, mapping.verification_state)
            self.assertEqual(record.timestamp, 123.0)

    def test_unknown_mapping_is_unknown_without_side_effect(self):
        collector = ContainmentObservationCollector()
        record = collector.observe(
            "future-path",
            trace_id="trace-test",
            session_id="session-test",
            timestamp=124.0,
        )
        self.assertEqual(record.source, "unknown")
        self.assertEqual(record.requested_action, "unknown")
        self.assertEqual(record.verification_state, ContainmentVerificationState.UNKNOWN)

    def test_record_is_immutable(self):
        record = ContainmentObservationCollector().observe(
            "manual-stop",
            trace_id="trace-test",
            session_id="session-test",
        )
        with self.assertRaises(FrozenInstanceError):
            record.source = "other"  # type: ignore[misc]

    def test_collector_has_no_physical_imports_or_calls(self):
        path = ROOT / "application" / "containment_observation.py"
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

    def test_observation_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_CONTAINMENT_OBSERVATION_RUNTIME.md").is_file())


if __name__ == "__main__":
    unittest.main()
