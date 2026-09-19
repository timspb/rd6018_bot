import ast
import unittest
from pathlib import Path

from application.active_session_parity import ActiveSessionParityObserver, ActiveSessionParityStatus
from application.operator_explanation import DecisionExplanationEngine


class Workstream32OperatorExplanationTests(unittest.TestCase):
    def setUp(self):
        observer = ActiveSessionParityObserver()
        self.observation = observer.ingest(persisted={"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}}, telemetry={"voltage": 17.14, "current": 3.48})
        self.parity = observer.compare(self.observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})

    def test_decision_and_phase_explanation_use_explicit_evidence(self):
        explanation = DecisionExplanationEngine().explain(observation=self.observation, parity=self.parity, evidence={"strategy": "MIX_HOLD", "reason": "Delta completed; hold evidence is active", "expected_next_transition": "TerminationDetected", "evidence": ("delta_completed", "hold_started"), "why_entered": "phase transition observed", "why_remains": "hold condition remains active", "transition_conditions": ("hold_complete",), "unmet_conditions": ("hold_complete",)})
        self.assertEqual("MIX_HOLD", explanation.decision.strategy)
        self.assertEqual("TerminationDetected", explanation.decision.expected_next_transition)
        self.assertEqual(("hold_complete",), explanation.phase.unmet_conditions)

    def test_missing_evidence_is_unknown_not_inferred(self):
        explanation = DecisionExplanationEngine().explain(observation=self.observation, parity=self.parity, evidence={})
        self.assertIsNone(explanation.decision.expected_next_transition)
        self.assertIn("next transition is not explicitly evidenced", explanation.unknown_reasons)
        self.assertEqual("UNKNOWN", explanation.safety.state)

    def test_historical_fault_is_separate_from_active_safety(self):
        explanation = DecisionExplanationEngine().explain(observation=self.observation, parity=self.parity, evidence={"safety_state": "NORMAL", "historical_faults": ("EMERGENCY_UNAVAILABLE at 03:15",), "protections": ("protection_code=0",)})
        self.assertEqual("NORMAL", explanation.safety.state)
        self.assertEqual(("EMERGENCY_UNAVAILABLE at 03:15",), explanation.safety.historical_faults)
        self.assertNotIn("EMERGENCY_UNAVAILABLE at 03:15", explanation.safety.blockers)

    def test_comparison_is_exposed(self):
        explanation = DecisionExplanationEngine().explain(observation=self.observation, parity=self.parity, evidence={"safety_state": "NORMAL"})
        self.assertEqual(ActiveSessionParityStatus.MATCH.value, explanation.comparison)

    def test_no_control_or_physical_path(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "operator_explanation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("output_on", "output_off", "turn_on", "turn_off", "controller.start", "controller.stop", "lease_renew", "send_command"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
