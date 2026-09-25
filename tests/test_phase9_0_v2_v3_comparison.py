"""Phase 9.0 V2/V3 comparison-only tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from application.v2_v3_comparison import (
    ComparisonContext,
    ComparisonStatus,
    DecisionSnapshot,
    V2V3ComparisonEngine,
)


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(**changes) -> DecisionSnapshot:
    values = {
        "fsm_state": "active", "phase": "main", "profile": "AGM",
        "strategy_decision": {"finish": "hold"},
        "target_values": {"voltage": 14.7, "current": 5.0},
        "safety_limits": {"max_voltage": 18.0, "max_current": 18.0},
        "warnings": (), "containment_recommendation": None,
        "actuator_intent": {"operation": "set_voltage", "target": 14.7},
        "trace_id": "trace-9",
    }
    values.update(changes)
    return DecisionSnapshot(**values)


class V2V3ComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ComparisonContext("trace-9", telemetry={"voltage": 14.2}, configuration={"profile": "AGM"}, session_context={"session": "s1"})

    def test_equal_scenario(self) -> None:
        result = V2V3ComparisonEngine(lambda _: _snapshot(), lambda _: _snapshot()).compare(self.context)
        self.assertEqual(ComparisonStatus.EQUAL, result.status)
        self.assertTrue(result.equal)
        self.assertEqual("trace-9", result.trace_id)

    def test_known_efb_conflict_is_expected_difference(self) -> None:
        v2 = _snapshot(profile="EFB", strategy_decision={"mix_budget_hours": 20})
        v3 = _snapshot(profile="EFB", strategy_decision={"mix_budget_hours": 24})
        result = V2V3ComparisonEngine(lambda _: v2, lambda _: v3, expected_differences={"strategy_decision"}).compare(self.context)
        self.assertEqual(ComparisonStatus.EXPECTED_DIFFERENCE, result.status)
        self.assertEqual("strategy_decision", result.differences[0].field)

    def test_known_cc_delta_conflict_is_expected_difference(self) -> None:
        v2 = _snapshot(strategy_decision={"cc_delta_v": 0.03})
        v3 = _snapshot(strategy_decision={"cc_delta_v": 0.05})
        result = V2V3ComparisonEngine(lambda _: v2, lambda _: v3, expected_differences={"strategy_decision"}).compare(self.context)
        self.assertEqual(ComparisonStatus.EXPECTED_DIFFERENCE, result.status)

    def test_safety_divergence_is_conflict(self) -> None:
        v2 = _snapshot(safety_limits={"max_voltage": 18.0, "max_current": 18.0})
        v3 = _snapshot(safety_limits={"max_voltage": 16.5, "max_current": 18.0})
        result = V2V3ComparisonEngine(lambda _: v2, lambda _: v3, expected_differences={"strategy_decision"}).compare(self.context)
        self.assertEqual(ComparisonStatus.CONFLICT, result.status)
        self.assertEqual("safety_limits", result.differences[0].field)

    def test_trace_correlation_and_unknown(self) -> None:
        result = V2V3ComparisonEngine(lambda _: None, lambda _: _snapshot()).compare(self.context)
        self.assertEqual(ComparisonStatus.UNKNOWN, result.status)
        self.assertEqual("trace-9", result.trace_id)

    def test_document_excludes_ui_and_transport_comparison(self) -> None:
        text = (ROOT / "docs" / "RD6018_V2_V3_SHADOW_COMPARISON_MODEL.md").read_text(encoding="utf-8")
        self.assertIn("UI, Telegram formatting and transport details", text)
        self.assertIn("expected_difference", text)


if __name__ == "__main__":
    unittest.main()
