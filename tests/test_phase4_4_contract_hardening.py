"""Contract-only tests for Phase 4.4 actuator hardening."""

from __future__ import annotations

import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)


ROOT = Path(__file__).resolve().parents[1]


def make_intent() -> ActuatorIntent:
    return ActuatorIntent.new(
        trace_id="trace-hardening",
        source="v2_transaction",
        requested_operation=ActuatorOperation.OUTPUT_OFF,
        target="RD6018 Output",
        reason="safety containment",
        owner="SafeOutputCoordinator",
        trigger=ActuatorTrigger.SAFETY_CONTAINMENT,
        rollback_policy=RollbackPolicy.CONTAIN_AND_LATCH,
        safety_context=SafetyContext("stale", "armed", "required", "unknown", "safety_limits"),
        verification_expectation=PhysicalVerificationExpectation("off", True, "safe_output_timeout"),
    )


class Phase44ContractHardeningTests(unittest.TestCase):
    def test_typed_contracts_are_immutable(self):
        intent = make_intent()
        with self.assertRaises(FrozenInstanceError):
            intent.trigger = ActuatorTrigger.WATCHDOG  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            intent.safety_context.lease_state = "expired"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            intent.verification_expectation.expected_state = "unknown"  # type: ignore[misc]

    def test_invalid_trigger_and_rollback_are_rejected(self):
        with self.assertRaises(ValueError):
            ActuatorTrigger("invalid")
        with self.assertRaises(ValueError):
            RollbackPolicy("invalid")
        payload = make_intent().to_dict()
        payload["trigger"] = "invalid"
        with self.assertRaises(ValueError):
            ActuatorIntent.from_dict(payload)
        payload = make_intent().to_dict()
        payload["rollback_policy"] = "invalid"
        with self.assertRaises(ValueError):
            ActuatorIntent.from_dict(payload)

    def test_missing_safety_context_is_rejected(self):
        with self.assertRaises(TypeError):
            ActuatorIntent(
                intent_id="intent",
                trace_id="trace",
                source="source",
                requested_operation=ActuatorOperation.OUTPUT_OFF,
                target="Output",
                reason="reason",
                owner="owner",
                trigger=ActuatorTrigger.STOP_REQUEST,
                rollback_policy=RollbackPolicy.SAFE_OFF,
                safety_context=None,  # type: ignore[arg-type]
                verification_expectation=PhysicalVerificationExpectation("off", True, "stop"),
            )

    def test_serialization_round_trip(self):
        intent = make_intent()
        restored = ActuatorIntent.from_dict(json.loads(json.dumps(intent.to_dict())))
        self.assertEqual(restored, intent)
        self.assertEqual(restored.to_dict(), intent.to_dict())

    def test_contract_layer_has_no_physical_imports(self):
        for filename in ("actuator_intent.py", "actuator_intent_adapter.py"):
            path = ROOT / "application" / filename
            tree = ast.parse(path.read_text(encoding="utf-8"))
            modules = []
            calls = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    modules.append(node.module or "")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
            self.assertTrue(all(not item.startswith(("hass_api", "runtime.physical", "safe_output")) for item in modules))
            self.assertTrue(calls.isdisjoint({"turn_on", "turn_off", "set_voltage", "set_current", "start", "stop"}))

    def test_hardening_document_exists(self):
        self.assertTrue((ROOT / "docs" / "RD6018_ACTUATOR_CONTRACT_HARDENING.md").is_file())


if __name__ == "__main__":
    unittest.main()
