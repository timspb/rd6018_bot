"""Phase 10.3 ownership transition model tests."""

from pathlib import Path
import unittest

from application.ownership_transition import (
    AuthorityOwner,
    MigrationMode,
    OwnershipTransitionPlan,
    TransitionComponent,
    default_transition_plan,
)


ROOT = Path(__file__).resolve().parents[1]


class OwnershipTransitionTests(unittest.TestCase):
    def test_authority_matrix_is_complete(self) -> None:
        plan = default_transition_plan()
        self.assertEqual(set(TransitionComponent), {entry.component for entry in plan.matrix})
        self.assertTrue(all(entry.target_owner is AuthorityOwner.V3 for entry in plan.matrix))
        self.assertFalse(plan.ownership_transfer_enabled)

    def test_no_implicit_ownership_transfer(self) -> None:
        plan = default_transition_plan()
        self.assertIs(AuthorityOwner.V2, plan.entry(TransitionComponent.PHYSICAL_OUTPUT).current_owner)
        self.assertIs(MigrationMode.CUTOVER, plan.entry(TransitionComponent.PHYSICAL_OUTPUT).migration_mode)
        with self.assertRaises(ValueError):
            OwnershipTransitionPlan(plan.matrix, plan.rollback_conditions, plan.dual_run_rules, plan.approval_gates, True)

    def test_rollback_path_exists_for_every_component(self) -> None:
        plan = default_transition_plan()
        self.assertTrue(plan.rollback_conditions)
        self.assertTrue(all(entry.rollback_conditions for entry in plan.matrix))
        self.assertTrue(plan.dual_run_rules)
        self.assertTrue(plan.approval_gates)

    def test_document_declares_matrix_and_gates(self) -> None:
        text = (ROOT / "docs" / "RD6018_OWNERSHIP_TRANSITION_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("Authority matrix", "Current owner", "Target owner", "Rollback conditions", "Dual-run", "explicit control approval"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
