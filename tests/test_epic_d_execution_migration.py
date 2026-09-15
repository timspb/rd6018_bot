"""EPIC D execution migration preparation tests; no physical integration."""

from pathlib import Path
import ast
import unittest

from application.actuator_intent import (
    ActuatorIntent,
    ActuatorOperation,
    ActuatorTrigger,
    PhysicalVerificationExpectation,
    RollbackPolicy,
    SafetyContext,
)
from application.execution_boundary import ExecutionDispatcher


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "RD6018_EXECUTION_MIGRATION_MODEL.md"
BOUNDARY = ROOT / "application" / "execution_boundary.py"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


def make_intent() -> ActuatorIntent:
    return ActuatorIntent.new(
        trace_id="epic-d-trace",
        source="v3-shadow",
        requested_operation=ActuatorOperation.OUTPUT_OFF,
        target={"output": False},
        reason="shadow parity",
        owner="V2 transaction owner",
        trigger=ActuatorTrigger.STOP_REQUEST,
        rollback_policy=RollbackPolicy.SAFE_OFF,
        safety_context=SafetyContext("fresh", "armed", "normal", "known", "limits-v2"),
        verification_expectation=PhysicalVerificationExpectation("off", True, "off-timeout"),
    )


class EpicDExecutionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = DOC.read_text(encoding="utf-8")

    def test_pipeline_gates_and_migration_modes_are_present(self) -> None:
        for term in (
            "ActuatorIntent", "Validation", "ExecutionRequest", "Adapter",
            "Physical command", "Readback", "Verification", "observe",
            "dry-run", "dual-run", "staged", "cutover", "rollback",
        ):
            self.assertIn(term, self.text)
        for term in ("valid `ActuatorIntent`", "approved execution owner", "typed `SafetyContext`", "explicit `RollbackPolicy`", "typed `PhysicalVerificationExpectation`"):
            self.assertIn(term, self.text)

    def test_intent_validation_and_ownership_checks(self) -> None:
        result = ExecutionDispatcher().dispatch_intent(make_intent())
        self.assertTrue(result.accepted)
        self.assertTrue(result.deferred)

        invalid_owner = make_intent()
        object.__setattr__(invalid_owner, "owner", "v3-physical-direct")
        rejected = ExecutionDispatcher().dispatch_intent(invalid_owner)
        self.assertTrue(rejected.rejected)
        self.assertIn("owner", rejected.reason)

    def test_rollback_and_verification_are_required(self) -> None:
        missing_rollback = make_intent()
        object.__setattr__(missing_rollback, "rollback_policy", None)
        self.assertTrue(ExecutionDispatcher().dispatch_intent(missing_rollback).rejected)

        missing_verification = make_intent()
        object.__setattr__(missing_verification, "verification_expectation", None)
        self.assertTrue(ExecutionDispatcher().dispatch_intent(missing_verification).rejected)

    def test_boundary_has_no_physical_or_transport_calls(self) -> None:
        tree = ast.parse(BOUNDARY.read_text(encoding="utf-8"), filename=str(BOUNDARY))
        forbidden_imports = ("hass_api", "homeassistant", "esphome", "rd_transport", "runtime.physical", "runtime.output", "telegram")
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        self.assertEqual([], [name for name in imports if any(item in name for item in forbidden_imports)])
        source = BOUNDARY.read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current(", "get_all_live(", "output_on(", "output_off("):
            self.assertNotIn(token, source)

    def test_document_and_canonical_status(self) -> None:
        for term in ("equal", "expected difference", "unsafe difference", "unknown", "NOT_READY_FOR_EXECUTION", "no physical calls"):
            self.assertIn(term, self.text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC D — Execution migration", canonical)
        self.assertIn("Current status: contract/shadow execution preparation", canonical)
        self.assertIn("V2 remains the execution and physical owner", canonical)


if __name__ == "__main__":
    unittest.main()
