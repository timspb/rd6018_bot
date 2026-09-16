"""EPIC H.0 execution shadow validation tests; no physical integration."""

import ast
from pathlib import Path
import unittest

from application.actuator_intent import (
    ActuatorIntent, ActuatorOperation, ActuatorTrigger,
    PhysicalVerificationExpectation, RollbackPolicy, SafetyContext,
)
from application.execution_shadow_validation import (
    ExecutionShadowValidator, FailureScenario, ShadowValidationCategory, V2ExecutionAction,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "execution_shadow_validation.py"
DOC = ROOT / "docs" / "RD6018_EXECUTION_SHADOW_VALIDATION_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


def make_intent(operation=ActuatorOperation.OUTPUT_OFF, *, owner="V2 transaction owner", rollback=RollbackPolicy.SAFE_OFF, verify=True):
    return ActuatorIntent.new(
        trace_id="h-trace", source="v3-shadow", requested_operation=operation,
        target={"value": False} if operation is ActuatorOperation.OUTPUT_OFF else {"value": 14.4},
        reason="shadow validation", owner=owner, trigger=ActuatorTrigger.SAFETY_CONTAINMENT,
        rollback_policy=rollback,
        safety_context=SafetyContext("fresh", "armed", "normal", "known", "limits-v2"),
        verification_expectation=PhysicalVerificationExpectation("off", verify, "readback-timeout"),
    )


def make_action(intent, *, transport=True, containment=False):
    return V2ExecutionAction(
        operation=intent.requested_operation, target=intent.target, owner=intent.owner,
        safety_context=intent.safety_context, rollback_policy=intent.rollback_policy,
        verification_expectation=intent.verification_expectation, adapter="v2-shadow-adapter",
        transport_available=transport, readback_required=True, containment=containment,
    )


class EpicHExecutionShadowValidationTests(unittest.TestCase):
    def test_intent_parity_for_operations_and_containment(self):
        validator = ExecutionShadowValidator()
        for operation in ActuatorOperation:
            intent = make_intent(operation)
            result = validator.compare(make_action(intent, containment=operation is ActuatorOperation.OUTPUT_OFF), intent)
            self.assertEqual(ShadowValidationCategory.EQUAL, result.category)
            self.assertFalse(result.physical_execution_performed)

    def test_safety_rollback_and_verification_validation(self):
        validator = ExecutionShadowValidator()
        intent = make_intent(rollback=RollbackPolicy.NONE, verify=False)
        result = validator.compare(make_action(intent), intent)
        self.assertFalse(result.safety_valid)
        self.assertFalse(result.execution_ready)

    def test_failure_scenarios_are_classified_without_execution(self):
        validator = ExecutionShadowValidator()
        intent = make_intent()
        action = make_action(intent)
        for scenario in FailureScenario:
            result = validator.validate_failure(scenario, action, intent)
            self.assertFalse(result.physical_execution_performed)
        unsafe = make_intent(rollback=RollbackPolicy.NONE, verify=False)
        result = validator.validate_failure(FailureScenario.READBACK_MISMATCH, make_action(unsafe), unsafe)
        self.assertEqual(ShadowValidationCategory.UNSAFE_DIFFERENCE, result.category)

    def test_unavailable_transport_is_unresolved(self):
        intent = make_intent()
        result = ExecutionShadowValidator().compare(make_action(intent, transport=False), intent)
        self.assertEqual(ShadowValidationCategory.UNRESOLVED, result.category)
        self.assertFalse(result.execution_ready)

    def test_no_physical_or_transport_calls(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("execution_boundary", "transport", "hass", "homeassistant", "esphome", "lease", "physical", "output")
        self.assertEqual([], [name for name in imports if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("dispatch(", "output_on(", "output_off(", "set_voltage(", "set_current(", "turn_on(", "turn_off(", "renew"):
            self.assertNotIn(token, source)

    def test_document_and_canonical_status(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("Intent parity", "Safety parity", "Execution readiness", "command timeout", "readback mismatch", "stale telemetry", "expired lease", "unavailable transport", "EXECUTION_SHADOW_VALIDATED"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC H.0 — Execution shadow validation", canonical)
        self.assertIn("Current status: execution shadow validation", canonical)


if __name__ == "__main__":
    unittest.main()
