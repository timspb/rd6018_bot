"""Static/data-only tests for Phase 4 actuator ownership preparation."""

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ExistingActuatorRequest,
    map_existing_request,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase4ActuatorOwnershipTests(unittest.TestCase):
    def test_intent_is_immutable_and_deeply_frozen(self):
        intent = ActuatorIntent.new(
            trace_id="trace-1",
            source="test",
            requested_operation=ActuatorOperation.SET_CURRENT,
            target=1.5,
            reason="phase transition",
            owner="v2_runtime_safety",
            safety_context={"output": False, "nested": {"fresh": True}},
        )
        with self.assertRaises(FrozenInstanceError):
            intent.owner = "other"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            intent.safety_context["output"] = True  # type: ignore[index]
        self.assertEqual(intent.safety_context["nested"]["fresh"], True)

    def test_all_operations_and_shadow_mapping(self):
        for operation in ActuatorOperation:
            intent = map_existing_request(
                ExistingActuatorRequest(
                    source="legacy",
                    operation=operation,
                    target=1.0,
                    reason="test",
                    owner="v2_owner",
                    safety_context={"checked": True},
                ),
                trace_id="trace-test",
            )
            self.assertEqual(intent.requested_operation, operation)
            self.assertEqual(intent.trace_id, "trace-test")

    def test_intent_layer_has_no_physical_imports_or_calls(self):
        path = ROOT / "application" / "actuator_intent.py"
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

    def test_ui_cannot_construct_execution_or_actuator_owner(self):
        violations = []
        for root in (ROOT / "telegram", ROOT / "runtime" / "ui"):
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                for name in ("ActuatorIntent", "HassClient", "PhysicalBridgeExecutor", "ProductionStartRunner"):
                    if name + "(" in source:
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual(violations, [])

    def test_ownership_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_ACTUATOR_OWNERSHIP_MODEL.md").is_file())


if __name__ == "__main__":
    unittest.main()
