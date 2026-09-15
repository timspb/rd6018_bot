"""Phase 10.1 analytical shadow evidence persistence tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from application.persistence_boundary import InMemoryPersistenceProvider, PersistenceKind, RestoreRejected
from application.production_shadow_observer import ShadowObservationSession
from application.shadow_evidence import ShadowEvidenceStore
from application.v2_v3_comparison import ComparisonContext, DecisionSnapshot


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(**changes) -> DecisionSnapshot:
    values = {
        "fsm_state": "active", "phase": "main", "profile": "AGM",
        "strategy_decision": {"finish": "hold"}, "target_values": {"voltage": 14.7},
        "safety_limits": {"max_voltage": 18.0}, "warnings": (),
        "containment_recommendation": None, "actuator_intent": {"operation": "set_voltage"},
        "trace_id": "trace-101",
    }
    values.update(changes)
    return DecisionSnapshot(**values)


class ShadowEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        context = ComparisonContext("trace-101", {"voltage": 14.2}, {"profile": "AGM"}, {"session": "s101"})
        self.observation = ShadowObservationSession(lambda _: _snapshot()).observe(context, _snapshot())
        self.store = ShadowEvidenceStore(InMemoryPersistenceProvider())

    def test_save_observation_and_namespace(self) -> None:
        evidence = self.store.save_observation(self.observation)
        self.assertEqual("shadow_evidence", evidence.namespace)
        self.assertEqual(64, len(evidence.input_snapshot_hash))
        self.assertEqual((evidence,), self.store.records)

    def test_query_history_and_trace_correlation(self) -> None:
        first = self.store.save_observation(self.observation)
        self.assertEqual((first,), self.store.query_history(trace_id="trace-101"))
        self.assertEqual((), self.store.query_history(trace_id="other"))
        self.assertEqual("trace-101", first.comparison.trace_id)
        self.assertEqual("trace-101", first.divergence_explanation.trace_id)

    def test_runtime_restore_usage_rejected(self) -> None:
        evidence = self.store.save_observation(self.observation)
        with self.assertRaises(RestoreRejected):
            self.store.restore_candidate(evidence)
        persisted = self.store._persistence.load("trace-101:" + evidence.input_snapshot_hash[:12])
        self.assertEqual(PersistenceKind.SHADOW_EVIDENCE, persisted.kind)
        with self.assertRaises(RestoreRejected):
            self.store._persistence.restore_candidate(persisted)

    def test_no_physical_calls_in_store(self) -> None:
        source = (ROOT / "application" / "shadow_evidence.py").read_text(encoding="utf-8").lower()
        for token in ("output_on(", "output_off(", "set_voltage(", "set_current(", "controller.start", "controller.stop", "ha_client", "esphome"):
            self.assertNotIn(token, source)

    def test_document_declares_analytical_only_storage(self) -> None:
        text = (ROOT / "docs" / "RD6018_SHADOW_EVIDENCE_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("shadow_evidence", "SHA-256", "restore_candidate", "historical data", "START"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
