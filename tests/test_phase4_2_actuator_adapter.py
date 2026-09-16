"""Dry-run tests for the ActuatorIntent -> V2 request adapter."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)
from application.actuator_intent_adapter import (
    ActuatorIntentAdapter,
    V2ActuatorExecutionRequest,
)


ROOT = Path(__file__).resolve().parents[1]


def make_intent(
    operation: ActuatorOperation = ActuatorOperation.SET_CURRENT,
    *,
    owner: str = "V2 runtime safety surface",
    source: str = "runtime_v2",
    safety_context: SafetyContext | None = None,
) -> ActuatorIntent:
    return ActuatorIntent.new(
        trace_id="trace-test",
        source=source,
        requested_operation=operation,
        target=1.5,
        reason="dry-run test",
        owner=owner,
        trigger=ActuatorTrigger.MANUAL_ACTION,
        rollback_policy=RollbackPolicy.SAFE_OFF,
        safety_context=safety_context or SafetyContext("fresh", "armed", "none", "not_requested", "test"),
        verification_expectation=PhysicalVerificationExpectation("unchanged", False, "none"),
    )


class Phase42ActuatorAdapterTests(unittest.TestCase):
    def test_valid_intent_is_accepted_as_data(self):
        request = ActuatorIntentAdapter().adapt(make_intent())
        self.assertIsInstance(request, V2ActuatorExecutionRequest)
        self.assertEqual(request.operation, ActuatorOperation.SET_CURRENT)
        self.assertEqual(request.trace_id, "trace-test")

    def test_all_operations_have_valid_owner_mapping(self):
        owners = {
            ActuatorOperation.OUTPUT_ON: "V2 transaction owner",
            ActuatorOperation.OUTPUT_OFF: "SafeOutputCoordinator",
            ActuatorOperation.SET_VOLTAGE: "V2 runtime safety surface",
            ActuatorOperation.SET_CURRENT: "diagnostic safety boundary",
        }
        for operation, owner in owners.items():
            request = ActuatorIntentAdapter().adapt(make_intent(operation, owner=owner))
            self.assertEqual(request.operation, operation)

    def test_invalid_owner_is_rejected(self):
        with self.assertRaises(ValueError):
            ActuatorIntentAdapter().adapt(make_intent(owner="arbitrary caller"))

    def test_blocked_source_and_safety_context_are_rejected(self):
        with self.assertRaises(ValueError):
            ActuatorIntentAdapter().adapt(make_intent(source="telegram"))
        with self.assertRaises(ValueError):
            ActuatorIntentAdapter().adapt(
                make_intent(safety_context=SafetyContext("fresh", "armed", "blocked", "not_requested", "test"))
            )

    def test_adapter_has_no_physical_side_effects_or_safe_output_import(self):
        path = ROOT / "application" / "actuator_intent_adapter.py"
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

    def test_safe_output_is_not_replaced(self):
        source = (ROOT / "safe_output.py").read_text(encoding="utf-8")
        self.assertIn("class SafeOutputCoordinator", source)

    def test_adapter_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_ACTUATOR_INTENT_ADAPTER_MODEL.md").is_file())


if __name__ == "__main__":
    unittest.main()
