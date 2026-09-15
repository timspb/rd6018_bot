"""Phase 10.2 shadow acceptance metric and status tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from application.shadow_acceptance import (
    AcceptanceStatus,
    AcceptanceThresholds,
    ConfigurationStability,
    ExecutionReadiness,
    ShadowAcceptanceModel,
    TransportReadiness,
)
from application.shadow_evidence import ShadowEvidenceStore
from application.production_shadow_observer import ShadowObservationSession
from application.v2_v3_comparison import ComparisonContext, DecisionSnapshot


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(**changes) -> DecisionSnapshot:
    values = {
        "fsm_state": "active", "phase": "main", "profile": "AGM",
        "strategy_decision": {"finish": "hold"}, "target_values": {"voltage": 14.7},
        "safety_limits": {"max_voltage": 18.0}, "warnings": (),
        "containment_recommendation": None, "actuator_intent": {"operation": "set_voltage"},
        "trace_id": "trace-102",
    }
    values.update(changes)
    return DecisionSnapshot(**values)


class ShadowAcceptanceTests(unittest.TestCase):
    def _evidence(self, v3_changes=None):
        context = ComparisonContext("trace-102", {"voltage": 14.2}, {"profile": "AGM"}, {"session": "s102"})
        observation = ShadowObservationSession(lambda _: _snapshot(**(v3_changes or {}))).observe(context, _snapshot())
        store = ShadowEvidenceStore()
        return (store.save_observation(observation),)

    def _ready_inputs(self):
        return {
            "configuration": ConfigurationStability(0, 0, 0),
            "transport": TransportReadiness(True, True, True),
            "execution": ExecutionReadiness(True, True, True),
            "thresholds": AcceptanceThresholds(minimum_observations=1),
        }

    def test_metric_calculation(self) -> None:
        result = ShadowAcceptanceModel().evaluate(self._evidence(), **self._ready_inputs())
        self.assertEqual(1, result.decision_parity.observations)
        self.assertEqual(1.0, result.decision_parity.equal_rate)
        self.assertEqual(0.0, result.decision_parity.unexpected_conflict_rate)

    def test_acceptance_states(self) -> None:
        model = ShadowAcceptanceModel()
        inputs = self._ready_inputs()
        self.assertEqual(AcceptanceStatus.NOT_READY, model.evaluate((), **inputs).status)
        self.assertEqual(AcceptanceStatus.SHADOW_ACCEPTED, model.evaluate(self._evidence(), **inputs).status)
        self.assertEqual(AcceptanceStatus.OWNERSHIP_CANDIDATE, model.evaluate(self._evidence(), ownership_approval=True, **inputs).status)

    def test_unresolved_blocker_handling(self) -> None:
        inputs = self._ready_inputs()
        inputs["configuration"] = ConfigurationStability(1, 0, 0)
        result = ShadowAcceptanceModel().evaluate(self._evidence(), **inputs)
        self.assertEqual(AcceptanceStatus.NOT_READY, result.status)
        self.assertIn("configuration_unresolved", result.blockers)

    def test_safety_conflict_blocks_acceptance(self) -> None:
        result = ShadowAcceptanceModel().evaluate(
            self._evidence({"safety_limits": {"max_voltage": 16.5}}),
            **self._ready_inputs(),
        )
        self.assertEqual(AcceptanceStatus.NOT_READY, result.status)
        self.assertIn("safety_parity_not_proven", result.blockers)

    def test_document_declares_ownership_unchanged(self) -> None:
        text = (ROOT / "docs" / "RD6018_SHADOW_ACCEPTANCE_MODEL.md").read_text(encoding="utf-8")
        for phrase in ("decision parity", "safety parity", "configuration stability", "transport readiness", "execution readiness", "does not change ownership"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
