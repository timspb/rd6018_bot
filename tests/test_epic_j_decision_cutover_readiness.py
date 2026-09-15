"""EPIC J Stage 1 readiness tests; no live ownership change."""

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.decision_cutover_readiness import (
    DecisionCutoverReadinessModel,
    ReadinessState,
    Stage1SafetyGates,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "decision_cutover_readiness.py"
DOC = ROOT / "docs" / "RD6018_DECISION_CUTOVER_READINESS_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


def all_gates():
    return Stage1SafetyGates(True, True, True, True, True)


class EpicJDecisionCutoverReadinessTests(unittest.TestCase):
    def test_stage1_validation_and_approval_required(self):
        model = DecisionCutoverReadinessModel()
        not_ready = model.prepare(Stage1SafetyGates(True, False, True, True, True))
        self.assertEqual(ReadinessState.NOT_READY, not_ready.state)
        with self.assertRaises(PermissionError):
            model.approve(operator="op", source="test", rollback_authority="v2")
        ready = model.prepare(all_gates())
        self.assertEqual(ReadinessState.READY, ready.state)
        approved = model.approve(
            operator="operator-1",
            source="bench-review",
            rollback_authority="V2",
            timestamp=datetime.now(timezone.utc),
        )
        self.assertEqual(ReadinessState.APPROVED_CANDIDATE, approved.state)
        self.assertEqual("V3-candidate", approved.decision_owner)
        self.assertEqual("V2", approved.execution_owner)
        self.assertEqual("V2", approved.physical_owner)
        self.assertFalse(approved.live_ownership_changed)

    def test_rollback_and_audit_history(self):
        model = DecisionCutoverReadinessModel()
        model.prepare(all_gates())
        model.approve(operator="operator-1", source="review", rollback_authority="V2")
        rolled = model.rollback(source="operator-1", reason="parity_blocker")
        self.assertEqual(ReadinessState.ROLLED_BACK, rolled.state)
        self.assertEqual("V2", rolled.decision_owner)
        self.assertEqual("V2", rolled.execution_owner)
        self.assertEqual("stage1_decision_rollback", rolled.transition_history[-1].event_type)

    def test_no_execution_or_physical_imports(self):
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

    def test_document_and_canonical_status(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("Stage 1 authority flow", "Approval mechanism", "Safety gates", "Rollback", "Observability", "live_ownership_changed=False", "STAGE1_READINESS_MODEL_READY"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC J — Decision cutover readiness", canonical)
        self.assertIn("Current status: Stage 1 readiness preparation", canonical)


if __name__ == "__main__":
    unittest.main()
