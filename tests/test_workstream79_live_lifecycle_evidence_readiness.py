import unittest
from pathlib import Path

from application.decision_audit import DecisionAuditTrail
from application.operator_graph import GraphViewModel
from application.operator_log import OperatorLogViewModel
from application.operator_panel import OperatorPanelState
from application.recovery import V3RecoveryCoordinator
from application.v3_observer_composition import V3ObserverComposition


ROOT = Path(__file__).resolve().parents[1]


class LiveLifecycleEvidenceReadinessTests(unittest.TestCase):
    def test_observer_is_armed_without_execution_dependency(self):
        observer = V3ObserverComposition()
        lifecycle = observer.startup()
        self.assertTrue(lifecycle.started)
        self.assertFalse(lifecycle.shutdown)
        observer.shutdown()

        source = (ROOT / "application" / "v3_observer_composition.py").read_text(encoding="utf-8")
        for forbidden in ("ExecutionDispatcher", "PhysicalExecution", "turn_on", "turn_off", "lease_writer"):
            self.assertNotIn(forbidden, source)

    def test_ui_graph_log_and_panel_contracts_are_available(self):
        self.assertTrue(hasattr(GraphViewModel, "from_samples"))
        self.assertTrue(hasattr(OperatorLogViewModel, "from_events"))
        self.assertTrue(hasattr(OperatorPanelState, "compose"))

    def test_audit_and_recovery_contracts_are_available(self):
        self.assertTrue(hasattr(DecisionAuditTrail, "replay"))
        self.assertTrue(hasattr(V3RecoveryCoordinator, "decide"))

    def test_required_readiness_documents_exist(self):
        required = (
            "RD6018_V3_OBSERVER_COMPOSITION_MODEL.md",
            "RD6018_OPERATOR_PANEL_COMPOSITION_INTEGRITY.md",
            "RD6018_OPERATOR_GRAPH_AND_LOG_MODEL.md",
            "RD6018_V3_DECISION_AUDIT_TRAIL_MODEL.md",
            "RD6018_V3_RECOVERY_CONTINUITY_MODEL.md",
        )
        for filename in required:
            self.assertTrue((ROOT / "docs" / filename).is_file(), filename)

    def test_readiness_does_not_claim_live_capture(self):
        report = (ROOT / "docs" / "RD6018_LIVE_LIFECYCLE_EVIDENCE_CAPTURE_READINESS.md").read_text(encoding="utf-8")
        self.assertIn("READY_FOR_LIVE_CYCLE_CAPTURE", report)
        self.assertIn("не запускается", report)


if __name__ == "__main__":
    unittest.main()
