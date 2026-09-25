"""Phase 10.0 production-shaped shadow observer tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from application.production_shadow_observer import ShadowObservationSession
from application.v2_v3_comparison import ComparisonContext, ComparisonStatus, DecisionSnapshot


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(**changes) -> DecisionSnapshot:
    values = {
        "fsm_state": "active", "phase": "main", "profile": "AGM",
        "strategy_decision": {"finish": "hold"},
        "target_values": {"voltage": 14.7, "current": 5.0},
        "safety_limits": {"max_voltage": 18.0}, "warnings": (),
        "containment_recommendation": None,
        "actuator_intent": {"operation": "set_voltage"}, "trace_id": "trace-10",
    }
    values.update(changes)
    return DecisionSnapshot(**values)


class ShadowObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ComparisonContext(
            "trace-10",
            telemetry={"voltage": 14.2, "current": 2.0},
            configuration={"profile": "AGM"},
            session_context={"session_id": "s10"},
        )
        self.v2 = _snapshot()
        self.session = ShadowObservationSession(lambda _: _snapshot())

    def test_observer_startup_and_mirrored_telemetry(self) -> None:
        self.assertEqual((), self.session.records)
        record = self.session.observe(self.context, self.v2)
        self.assertEqual(self.context.telemetry, dict(record.input_snapshot))
        self.assertEqual("trace-10", record.trace_id)
        self.assertEqual("trace-10", record.diagnostic.correlation.trace_id)

    def test_decision_comparison_and_divergence_recording(self) -> None:
        session = ShadowObservationSession(lambda _: _snapshot(strategy_decision={"cc_delta_v": 0.05}))
        record = session.observe(self.context, self.v2)
        self.assertEqual(ComparisonStatus.CONFLICT, record.comparison.status)
        self.assertEqual(1, len(record.explanation.explanations))
        self.assertEqual((record,), session.records)

    def test_diagnostics_flow(self) -> None:
        record = self.session.observe(self.context, self.v2)
        self.assertEqual("shadow_observation_recorded", record.diagnostic.event_type)
        self.assertEqual("v3-shadow-observer", record.diagnostic.source)

    def test_no_execution_or_production_side_effects(self) -> None:
        source = (ROOT / "application" / "production_shadow_observer.py").read_text(encoding="utf-8")
        for token in ("ExecutionDispatcher", "output_on(", "output_off(", "set_voltage(", "set_current(", "ha_client", "esphome", "asyncio.run"):
            self.assertNotIn(token, source)

    def test_document_declares_shadow_only_boundary(self) -> None:
        text = (ROOT / "docs" / "RD6018_PRODUCTION_SHADOW_OBSERVER_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("ShadowObservationSession", "V2 decision", "V3 decision", "divergence", "does not execute"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
