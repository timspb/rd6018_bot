"""WORKSTREAM 2 boundary contracts and inventories; no runtime wiring."""

import ast
from pathlib import Path
import unittest

from application.actuator_intent import ActuatorOperation
from application.configuration_decision_registry import unresolved_configuration_decisions
from application.legacy_actuator_boundary import legacy_actuator_compatibility_paths
from application.safety_boundary import (
    SAFETY_DECISION_OWNER,
    SAFETY_OWNERSHIP_INVENTORY,
    SafetySignal,
    SafetySignalKind,
    SafetyDecisionAction,
    containment_request,
    decide,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "RD6018_V3_FINAL_ARCHITECTURE_AUDIT.md"
UI_PROVIDER = ROOT / "application" / "operator_snapshot_provider.py"


class Workstream2BoundaryCleanupTests(unittest.TestCase):
    def test_ui_provider_has_only_explicit_observation_import(self):
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
        self.assertIn("operator_observation_source", imports)
        self.assertNotIn("legacy_ui_boundary", imports)

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

    def test_safety_inventory_has_one_canonical_decision_owner(self):
        self.assertGreaterEqual(len(SAFETY_OWNERSHIP_INVENTORY), 8)
        self.assertEqual({SAFETY_DECISION_OWNER}, {item.decision_owner for item in SAFETY_OWNERSHIP_INVENTORY})
        self.assertTrue(all(not item.physical_write_allowed for item in SAFETY_OWNERSHIP_INVENTORY))

    def test_configuration_conflicts_are_explicit_and_unresolved(self):
        decisions = unresolved_configuration_decisions()
        self.assertGreaterEqual(len(decisions), 6)
        self.assertTrue(all(item.status.value in {"RESOLVED", "UNRESOLVED", "MIGRATION_REQUIRED"} for item in decisions))
        self.assertTrue(any(item.key == "safety.watchdog_timeout_s" for item in decisions))
        self.assertTrue(any(item.key == "lease.renewal_interval" for item in decisions))
        self.assertEqual({"RESOLVED", "UNRESOLVED", "MIGRATION_REQUIRED"}, {item.status.value for item in decisions})

    def test_domain_imports_use_explicit_legacy_adapter(self):
        for name in ("charge_orchestration.py", "shadow_composition.py"):
            text = (ROOT / "application" / name).read_text(encoding="utf-8")
            self.assertNotIn("from runtime.charge", text)
            self.assertIn("legacy_domain_adapter", text)

    def test_application_has_no_implicit_runtime_start(self):
        for path in (ROOT / "application").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual((getattr(node.func.value, "id", ""), node.func.attr), ("asyncio", "run"), path.name)
            self.assertNotIn("runtime.v2_runtime", imports, path.name)

    def test_report_keeps_remaining_blockers_visible(self):
        text = AUDIT.read_text(encoding="utf-8")
        for marker in ("ACT-B01", "CFG-B01", "SAFE-B01", "RUN-B01", "Stage 1", "BLOCKED"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
