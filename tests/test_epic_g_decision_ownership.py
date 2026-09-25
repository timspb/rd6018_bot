"""EPIC G decision ownership preparation tests; no execution integration."""

import ast
from pathlib import Path
import unittest

from application.decision_authority import (
    DecisionAuthorityCoordinator,
    DecisionAuthorityMode,
    DecisionOwner,
)
from application.v2_v3_comparison import ComparisonContext, DecisionSnapshot


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "decision_authority.py"
DOC = ROOT / "docs" / "RD6018_DECISION_OWNERSHIP_MIGRATION_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


def decision(trace_id: str, *, phase: str = "main") -> DecisionSnapshot:
    return DecisionSnapshot("main", phase, "AGM", {"phase": phase}, {"voltage": 14.8}, {"max": 15.0}, trace_id=trace_id)


def context(trace_id: str = "decision-trace") -> ComparisonContext:
    return ComparisonContext(trace_id, {"voltage": 14.8}, {"profile": "AGM"}, {"session": "s1"})


class EpicGDecisionOwnershipTests(unittest.TestCase):
    def test_initial_authority_is_v2_shadow(self) -> None:
        coordinator = DecisionAuthorityCoordinator()
        self.assertEqual(DecisionAuthorityMode.SHADOW, coordinator.mode)
        self.assertEqual(DecisionOwner.V2, coordinator.owner)

    def test_parity_and_provenance_keep_v2_authoritative(self) -> None:
        coordinator = DecisionAuthorityCoordinator()
        result = coordinator.evaluate(context(), decision("decision-trace"), decision("decision-trace"))
        self.assertEqual(DecisionOwner.V2, result.owner)
        self.assertIs(result.selected, result.v2)
        self.assertEqual("equal", result.comparison.status.value)
        self.assertEqual("decision-trace", result.provenance.trace_id)

    def test_v3_modes_require_explicit_approval_and_missing_v3_never_takes_v2(self) -> None:
        coordinator = DecisionAuthorityCoordinator()
        with self.assertRaises(PermissionError):
            coordinator.set_mode(DecisionAuthorityMode.STAGED)
        coordinator.set_mode(DecisionAuthorityMode.STAGED, explicit_approval=True)
        self.assertEqual(DecisionOwner.V3, coordinator.owner)
        result = coordinator.evaluate(context(), decision("decision-trace"), None)
        self.assertIsNone(result.selected)
        self.assertIn("no_implicit_v2_takeover", result.provenance.reason)

    def test_rollback_returns_v2_authority(self) -> None:
        coordinator = DecisionAuthorityCoordinator()
        coordinator.set_mode(DecisionAuthorityMode.ACTIVE_DECISION, explicit_approval=True)
        provenance = coordinator.rollback_to_v2(reason="parity_conflict")
        self.assertEqual(DecisionOwner.V2, coordinator.owner)
        self.assertEqual(DecisionAuthorityMode.SHADOW, coordinator.mode)
        self.assertEqual("parity_conflict", provenance.reason)

    def test_no_execution_or_physical_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("execution", "controller", "hass", "homeassistant", "esphome", "lease", "physical", "output")
        self.assertEqual([], [name for name in imports if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("dispatch(", "output_on(", "output_off(", "set_voltage(", "set_current(", "renew"):
            self.assertNotIn(token, source)

    def test_document_and_canonical_status(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for term in ("FSM decision", "phase transition", "strategy decision", "termination decision", "safety recommendation", "containment recommendation", "V3 decision != physical execution", "DECISION_SHADOW_READY"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC G — Decision ownership migration", canonical)
        self.assertIn("Current status: decision ownership shadow preparation", canonical)


if __name__ == "__main__":
    unittest.main()
