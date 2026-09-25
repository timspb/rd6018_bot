"""EPIC I staged ownership model tests; no live authority changes."""

import ast
from pathlib import Path
import unittest

from application.staged_ownership import OwnershipStage, StagedOwnershipCutoverModel


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "staged_ownership.py"
DOC = ROOT / "docs" / "RD6018_STAGED_OWNERSHIP_CUTOVER_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


def gates(model, stage):
    return {gate: True for gate in model._gates(stage)}


class EpicIStagedOwnershipTests(unittest.TestCase):
    def test_transition_validity_is_sequential_and_gated(self):
        model = StagedOwnershipCutoverModel()
        skipped = model.transition(OwnershipStage.STAGE_2_EXECUTION_STAGED, {})
        self.assertFalse(skipped.accepted)
        self.assertIn("sequential_transition_required", skipped.missing_gates)
        missing = model.transition(OwnershipStage.STAGE_1_DECISION, {})
        self.assertFalse(missing.accepted)
        self.assertIn("decision_approval", missing.missing_gates)
        accepted = model.transition(OwnershipStage.STAGE_1_DECISION, gates(model, OwnershipStage.STAGE_1_DECISION))
        self.assertTrue(accepted.accepted)
        self.assertEqual("V3", accepted.ownership.decision_owner)
        self.assertEqual("V2", accepted.ownership.execution_owner)

    def test_rollback_path_returns_to_stage_zero(self):
        model = StagedOwnershipCutoverModel()
        model.transition(OwnershipStage.STAGE_1_DECISION, gates(model, OwnershipStage.STAGE_1_DECISION))
        result = model.rollback({"v2_healthy": True, "rollback_verified": True, "no_ambiguous_session": True})
        self.assertTrue(result.accepted)
        self.assertEqual(OwnershipStage.STAGE_0_SHADOW, model.stage)
        self.assertEqual("V2", model.ownership.decision_owner)

    def test_ownership_conflict_detection_and_single_physical_owner(self):
        model = StagedOwnershipCutoverModel()
        conflicts = model.validate_ownership(model.ownership)
        self.assertEqual((), conflicts)
        invalid = model.ownership.__class__("V3", "V3", "BOTH", "V2", "V3", "V3")
        self.assertIn("invalid_physical_owner", model.validate_ownership(invalid))
        stage2 = model._ownership_for(OwnershipStage.STAGE_2_EXECUTION_STAGED)
        self.assertEqual("V2", stage2.physical_owner)
        self.assertEqual("V2", stage2.lease_owner)

    def test_no_runtime_or_physical_imports(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("runtime", "execution", "controller", "hass", "homeassistant", "esphome", "lease", "physical", "output")
        self.assertEqual([], [name for name in imports if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("dispatch(", "output_on(", "output_off(", "set_voltage(", "set_current(", "renew"):
            self.assertNotIn(token, source)

    def test_document_and_canonical_status(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("Stage 0", "Stage 1", "Stage 2", "Stage 3", "no implicit", "one physical execution owner", "one lease owner", "CUTOVER_MODEL_DEFINED"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC I — Staged ownership cutover", canonical)
        self.assertIn("Current status: staged cutover model", canonical)


if __name__ == "__main__":
    unittest.main()
