"""Phase 8.1 execution boundary routing tests; no physical integration."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)
from application.execution_boundary import ContainmentResultRequest, ExecutionDispatcher
from application.containment_result import ContainmentVerificationState


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "application" / "execution_boundary.py"


def _intent(owner: str = "V2 transaction owner") -> ActuatorIntent:
    return ActuatorIntent.new(
        trace_id="trace-1",
        source="v2-runtime",
        requested_operation=ActuatorOperation.OUTPUT_OFF,
        target={"output": False},
        reason="controlled stop",
        owner=owner,
        trigger=ActuatorTrigger.STOP_REQUEST,
        rollback_policy=RollbackPolicy.SAFE_OFF,
        safety_context=SafetyContext("fresh", "armed", "normal", "known", "limits-v1"),
        verification_expectation=PhysicalVerificationExpectation("off", True, "off-timeout"),
    )


class ExecutionBoundaryTests(unittest.TestCase):
    def test_intent_routing_is_deferred(self) -> None:
        result = ExecutionDispatcher().dispatch_intent(_intent(), correlation={"case": "intent"})
        self.assertTrue(result.accepted)
        self.assertTrue(result.deferred)
        self.assertFalse(result.rejected)
        self.assertEqual("trace-1", result.request.trace_id)
        self.assertEqual(ContainmentVerificationState.NOT_REQUESTED, result.verification_state)

    def test_containment_routing_is_deferred(self) -> None:
        request = ContainmentResultRequest(
            trace_id="trace-2",
            source="runtime-safety",
            trigger="watchdog",
            requested_action="verified_off",
            owner="V2 watchdog + safety",
            safety_context=SafetyContext("degraded", "expired", "required", "unknown", "limits-v1"),
            rollback_policy=RollbackPolicy.CONTAIN_AND_LATCH,
            verification_expectation=PhysicalVerificationExpectation("off", True, "containment-timeout"),
        )
        result = ExecutionDispatcher().dispatch_containment(request)
        self.assertTrue(result.accepted)
        self.assertTrue(result.deferred)
        self.assertEqual("watchdog", result.request.trigger)

    def test_invalid_owner_is_rejected(self) -> None:
        result = ExecutionDispatcher().dispatch_intent(_intent("telegram"))
        self.assertFalse(result.accepted)
        self.assertTrue(result.rejected)
        self.assertIn("owner", result.reason)

    def test_missing_safety_context_is_rejected(self) -> None:
        intent = _intent()
        object.__setattr__(intent, "safety_context", None)
        result = ExecutionDispatcher().dispatch_intent(intent)
        self.assertTrue(result.rejected)
        self.assertIn("safety context", result.reason)

    def test_boundary_has_no_infrastructure_or_physical_imports(self) -> None:
        tree = ast.parse(BOUNDARY.read_text(encoding="utf-8"), filename=str(BOUNDARY))
        forbidden = ("hass_api", "homeassistant", "esphome", "rd_transport", "runtime.physical", "runtime.output", "telegram", "database", "persistence")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        self.assertEqual([], [name for name in imports if any(token in name.lower() for token in forbidden)])
        source = BOUNDARY.read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current(", "get_all_live("):
            self.assertNotIn(token, source)

    def test_document_tracks_boundary_contract(self) -> None:
        text = (ROOT / "docs" / "RD6018_EXECUTION_BOUNDARY_MODEL.md").read_text(encoding="utf-8")
        for term in ("ExecutionDispatcher", "ExecutionRequest", "ExecutionResult", "deferred", "Physical execution is forbidden"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
