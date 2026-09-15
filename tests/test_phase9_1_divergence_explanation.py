"""Phase 9.1 comparison divergence explanation tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from application.divergence_explanation import DivergenceCategory, DivergenceExplanationEngine
from application.v2_v3_comparison import ComparisonContext, ComparisonStatus, DecisionSnapshot, V2V3ComparisonEngine


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(**changes) -> DecisionSnapshot:
    values = {
        "fsm_state": "active", "phase": "main", "profile": "AGM",
        "strategy_decision": {"finish": "hold"},
        "target_values": {"voltage": 14.7, "current": 5.0},
        "safety_limits": {"max_voltage": 18.0}, "warnings": (),
        "containment_recommendation": None,
        "actuator_intent": {"operation": "set_voltage"}, "trace_id": "trace-91",
    }
    values.update(changes)
    return DecisionSnapshot(**values)


class DivergenceExplanationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ComparisonContext("trace-91", {"voltage": 14.2}, {"profile": "AGM"}, {"session": "s1"})
        self.engine = DivergenceExplanationEngine()

    def _compare(self, v2, v3, expected=frozenset()):
        return V2V3ComparisonEngine(lambda _: v2, lambda _: v3, expected_differences=expected).compare(self.context)

    def test_explain_equal(self) -> None:
        result = self._compare(_snapshot(), _snapshot())
        analysis = self.engine.explain(result, self.context)
        self.assertEqual(ComparisonStatus.EQUAL, analysis.status)
        self.assertEqual((), analysis.explanations)
        self.assertEqual("trace-91", analysis.trace_id)

    def test_explain_expected_efb_conflict(self) -> None:
        result = self._compare(
            _snapshot(profile="EFB", strategy_decision={"mix_budget_hours": 20}),
            _snapshot(profile="EFB", strategy_decision={"mix_budget_hours": 24}),
            {"strategy_decision"},
        )
        explanation = self.engine.explain(result, self.context).explanations[0]
        self.assertEqual(DivergenceCategory.STRATEGY_DIFF, explanation.category)
        self.assertTrue(explanation.expected)
        self.assertIn("20 h", explanation.reason)

    def test_explain_safety_divergence(self) -> None:
        result = self._compare(_snapshot(safety_limits={"max_voltage": 18}), _snapshot(safety_limits={"max_voltage": 16.5}))
        explanation = self.engine.explain(result, self.context).explanations[0]
        self.assertEqual(DivergenceCategory.SAFETY_DIFF, explanation.category)
        self.assertFalse(explanation.expected)

    def test_explain_unknown_and_trace_mismatch(self) -> None:
        result = self._compare(_snapshot(strategy_decision={"new_policy": 1}), _snapshot(strategy_decision={"other_policy": 2}))
        explanation = self.engine.explain(result, self.context).explanations[0]
        self.assertEqual(DivergenceCategory.STRATEGY_DIFF, explanation.category)
        mismatch_context = ComparisonContext("different-trace", {}, {}, {})
        analysis = self.engine.explain(result, mismatch_context)
        self.assertEqual(ComparisonStatus.UNKNOWN, analysis.status)
        self.assertEqual(DivergenceCategory.UNKNOWN, analysis.explanations[0].category)

    def test_document_contains_known_conflicts(self) -> None:
        text = (ROOT / "docs" / "RD6018_V2_V3_DIVERGENCE_ANALYSIS.md").read_text(encoding="utf-8")
        for phrase in ("20 h", "24 h", "Vmax/Delta", "current-drop", "180 s", "300 s", "readback"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
