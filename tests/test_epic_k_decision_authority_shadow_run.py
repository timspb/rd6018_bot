"""EPIC K decision-authority rehearsal tests; no live takeover."""

import ast
from pathlib import Path
import unittest

from application.decision_authority_shadow_run import (
    DecisionAuthorityShadowRunner,
    ShadowFailure,
    ShadowRunStatus,
)
from application.v2_v3_comparison import ComparisonContext, DecisionSnapshot


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "decision_authority_shadow_run.py"
DOC = ROOT / "docs" / "RD6018_DECISION_AUTHORITY_SHADOW_RUN_MODEL.md"


def decision(trace_id: str, *, phase: str = "main", voltage: float = 14.8) -> DecisionSnapshot:
    return DecisionSnapshot(
        "main", phase, "AGM", {"phase": phase}, {"voltage": voltage},
        {"max": 15.0}, trace_id=trace_id,
    )


def context(trace_id: str = "shadow-k-1") -> ComparisonContext:
    return ComparisonContext(trace_id, {"voltage": 14.8}, {"profile": "AGM"}, {"session": "s1"})


class EpicKDecisionAuthorityShadowRunTests(unittest.TestCase):
    def test_shadow_transition_prepares_but_does_not_transfer_authority(self):
        result = DecisionAuthorityShadowRunner().run(context(), decision("shadow-k-1"), decision("shadow-k-1"))
        self.assertEqual(ShadowRunStatus.READY, result.status)
        self.assertEqual("V2", result.current_authority)
        self.assertEqual("V3", result.candidate_authority)
        self.assertEqual("V3", result.provenance.authority)
        self.assertEqual("V2", result.handoff.execution_owner)
        self.assertFalse(result.handoff.dispatched)
        self.assertFalse(result.live_decision_ownership_changed)

    def test_warning_and_blocked_failure_scenarios(self):
        runner = DecisionAuthorityShadowRunner(expected_differences={"phase", "strategy_decision"})
        warning = runner.run(context(), decision("shadow-k-1"), decision("shadow-k-1", phase="cv"))
        self.assertEqual(ShadowRunStatus.WARNING, warning.status)
        unavailable = runner.run(context("shadow-k-2"), decision("shadow-k-2"), None, failure=ShadowFailure.V3_UNAVAILABLE)
        self.assertEqual(ShadowRunStatus.BLOCKED, unavailable.status)
        self.assertIsNone(unavailable.v3_canonical_decision)
        self.assertIsNone(unavailable.handoff)

    def test_rollback_is_visible_and_keeps_v2_current(self):
        result = DecisionAuthorityShadowRunner().run(
            context(), decision("shadow-k-1"), decision("shadow-k-1"), failure=ShadowFailure.ROLLBACK_REQUEST,
        )
        self.assertEqual(ShadowRunStatus.BLOCKED, result.status)
        self.assertEqual("V2", result.current_authority)
        self.assertEqual("REQUESTED", result.rollback_state)
        self.assertEqual("shadow_rehearsal_completed", result.transition_history[-1].event_type)
        self.assertFalse(result.live_decision_ownership_changed)

    def test_no_execution_or_physical_imports(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((node.module or "").lower())
        forbidden = ("controller", "execution", "hass", "homeassistant", "esphome", "lease", "transport", "physical", "output")
        self.assertEqual([], [name for name in imported if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("dispatch(", "output_on(", "output_off(", "set_voltage(", "set_current(", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)

    def test_document_covers_shadow_run_contract(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("Decision flow", "Hypothetical Stage 1", "Transition events", "Operator visibility", "Failure scenarios", "READY", "WARNING", "BLOCKED", "LIVE_DECISION_OWNERSHIP_UNCHANGED"):
            self.assertIn(term, text)


if __name__ == "__main__":
    unittest.main()
