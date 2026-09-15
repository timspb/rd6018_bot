"""WORKSTREAM 2 boundary contracts and inventories; no runtime wiring."""

import ast
from pathlib import Path
import unittest

from application.actuator_intent import ActuatorOperation
from application.configuration_decision_registry import unresolved_configuration_decisions
from application.legacy_actuator_boundary import legacy_actuator_compatibility_paths
from application.safety_boundary import SafetySignal, SafetySignalKind, SafetyDecisionAction, containment_request, decide


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "RD6018_V3_FINAL_ARCHITECTURE_AUDIT.md"
UI_PROVIDER = ROOT / "application" / "operator_snapshot_provider.py"


class Workstream2BoundaryCleanupTests(unittest.TestCase):
    def test_ui_provider_has_only_explicit_compatibility_import(self):
        tree = ast.parse(UI_PROVIDER.read_text(encoding="utf-8"), filename=str(UI_PROVIDER))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertNotIn("operator_hmi", imports)
        self.assertNotIn("rd6018_telemetry", imports)
        self.assertNotIn("runtime.diagnostics", imports)
        self.assertNotIn("runtime.journal", imports)
        self.assertIn("legacy_ui_boundary", imports)

    def test_all_legacy_actuator_paths_are_inventory_only(self):
        paths = legacy_actuator_compatibility_paths()
        self.assertGreaterEqual(len(paths), 10)
        self.assertEqual({ActuatorOperation.OUTPUT_ON, ActuatorOperation.OUTPUT_OFF, ActuatorOperation.SET_VOLTAGE, ActuatorOperation.SET_CURRENT}, {path.operation for path in paths})
        self.assertTrue(all(not path.dispatch_enabled for path in paths))
        self.assertTrue(all(path.adapter_boundary for path in paths))

    def test_safety_flow_is_detection_decision_request_data_only(self):
        decision = decide(SafetySignal(SafetySignalKind.TELEMETRY, "test", False, "stale"), trace_id="t1")
        self.assertEqual(SafetyDecisionAction.CONTAIN, decision.action)
        request = containment_request(decision)
        self.assertEqual("Safety Decision Authority", request.decision_owner)
        self.assertEqual("t1", request.trace_id)

    def test_configuration_conflicts_are_explicit_and_unresolved(self):
        decisions = unresolved_configuration_decisions()
        self.assertGreaterEqual(len(decisions), 6)
        self.assertTrue(all(item.status.value == "UNRESOLVED" for item in decisions))
        self.assertTrue(any(item.key == "safety.watchdog_timeout_s" for item in decisions))
        self.assertTrue(any(item.key == "lease.renewal_interval" for item in decisions))

    def test_report_keeps_remaining_blockers_visible(self):
        text = AUDIT.read_text(encoding="utf-8")
        for marker in ("ACT-B01", "CFG-B01", "SAFE-B01", "RUN-B01", "Stage 1", "BLOCKED"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
