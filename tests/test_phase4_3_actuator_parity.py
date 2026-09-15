"""Analysis tests for ActuatorIntentAdapter field parity."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from application.actuator_intent import ActuatorIntent, ActuatorOperation
from application.actuator_intent_adapter import ActuatorIntentAdapter


ROOT = Path(__file__).resolve().parents[1]


class Phase43ActuatorParityTests(unittest.TestCase):
    def make_intent(self, operation: ActuatorOperation, *, safety_context=None, owner=None):
        owners = {
            ActuatorOperation.OUTPUT_ON: "V2 transaction owner",
            ActuatorOperation.OUTPUT_OFF: "SafeOutputCoordinator",
            ActuatorOperation.SET_VOLTAGE: "V2 runtime safety surface",
            ActuatorOperation.SET_CURRENT: "V2 runtime safety surface",
        }
        return ActuatorIntent.new(
            trace_id="trace-parity",
            source="v2_transaction",
            requested_operation=operation,
            target=14.8 if operation is ActuatorOperation.SET_VOLTAGE else 5.0 if operation is ActuatorOperation.SET_CURRENT else "RD6018 Output",
            reason="parity analysis",
            owner=owner or owners[operation],
            safety_context=safety_context or {
                "ownership": "available",
                "fresh_readback": True,
                "rollback": "verified_off",
            },
        )

    def test_request_equivalence_for_all_operations(self):
        adapter = ActuatorIntentAdapter()
        for operation in ActuatorOperation:
            intent = self.make_intent(operation)
            request = adapter.adapt(intent)
            self.assertEqual(request.source, intent.source)
            self.assertEqual(request.owner, intent.owner)
            self.assertEqual(request.operation, intent.requested_operation)
            self.assertEqual(request.target, intent.target)
            self.assertEqual(request.reason, intent.reason)
            self.assertEqual(dict(request.safety_context), dict(intent.safety_context))

    def test_unsafe_owner_and_source_are_rejected(self):
        adapter = ActuatorIntentAdapter()
        with self.assertRaises(ValueError):
            adapter.adapt(self.make_intent(ActuatorOperation.OUTPUT_ON, owner="UI"))
        with self.assertRaises(ValueError):
            adapter.adapt(self.make_intent(ActuatorOperation.OUTPUT_OFF, owner="direct_physical"))
        with self.assertRaises(ValueError):
            adapter.adapt(
                ActuatorIntent.new(
                    trace_id="trace-parity",
                    source="v2_transaction",
                    requested_operation=ActuatorOperation.SET_CURRENT,
                    target=5.0,
                    reason="blocked",
                    owner="V2 runtime safety surface",
                    safety_context={"blocked": True},
                )
            )

    def test_missing_safety_context_is_rejected_before_adapter(self):
        with self.assertRaises(TypeError):
            ActuatorIntent.new(
                trace_id="trace-parity",
                source="v2_transaction",
                requested_operation=ActuatorOperation.OUTPUT_OFF,
                target="RD6018 Output",
                reason="missing context",
                owner="SafeOutputCoordinator",
                safety_context=None,  # type: ignore[arg-type]
            )

    def test_adapter_has_no_physical_side_effects(self):
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

    def test_parity_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_ACTUATOR_EXECUTION_PARITY.md").is_file())


if __name__ == "__main__":
    unittest.main()
