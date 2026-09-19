import ast
import unittest
from pathlib import Path

from application.active_session_parity import ActiveSessionParityObserver
from application.operator_dashboard_composer import OperatorDashboardComposer
from application.operator_explanation import DecisionExplanationEngine


class Workstream33OperatorDashboardTests(unittest.TestCase):
    def setUp(self):
        observer = ActiveSessionParityObserver()
        observation = observer.ingest(persisted={"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}}, telemetry={"voltage": 17.14, "current": 3.48, "temperature": 35.0, "source": "HA+ESP"}, rd={"phase": "mix"}, esphome={"output": True}, ha={"available": True})
        parity = observer.compare(observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})
        from application.operator_runtime_view import OperatorRuntimeViewComposer
        runtime_view = OperatorRuntimeViewComposer().compose(observation=observation, parity=parity, shadow={"stale_sources": ("HA",), "lease": {"armed": True}})
        explanation = DecisionExplanationEngine().explain(observation=observation, parity=parity, evidence={"safety_state": "NORMAL", "strategy": "MIX_HOLD", "reason": "explicit evidence"})
        self.state = OperatorDashboardComposer().compose(runtime_view=runtime_view, explanation=explanation, canary={"status": "BLOCKED", "blockers": ("CB-EVIDENCE-001",)}, timestamp=100)

    def test_single_snapshot_contains_all_panels(self):
        self.assertEqual(100, self.state.timestamp)
        self.assertEqual(("Baic72", "mix", "active"), (self.state.current_session.profile, self.state.current_session.phase, self.state.current_session.state))
        self.assertEqual(59.6472, round(self.state.telemetry.power, 4))
        self.assertEqual("MIX_HOLD", self.state.explanation.decision.strategy)
        self.assertEqual("MATCH", self.state.parity.status)
        self.assertEqual("BLOCKED", self.state.canary.status)

    def test_all_panels_share_current_snapshot_data(self):
        self.assertEqual(self.state.telemetry.stale_indicators, self.state.safety.stale)
        self.assertEqual(self.state.current_session.identity_status, "LEGACY_NO_IDENTITY")
        self.assertTrue(self.state.observe_only)

    def test_degraded_values_are_visible_not_guessed(self):
        self.assertEqual("UNKNOWN", self.state.timeline.session_id)
        self.assertEqual(0, self.state.timeline.event_count)
        self.assertEqual(("HA",), self.state.telemetry.stale_indicators)

    def test_diagnostics_and_canary_are_preserved(self):
        self.assertEqual(("CB-EVIDENCE-001",), self.state.canary.blockers)
        self.assertEqual(("HA",), self.state.diagnostics.stale_sources)

    def test_no_command_or_physical_path(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "operator_dashboard_composer.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("output_on", "output_off", "turn_on", "turn_off", "controller.start", "controller.stop", "lease_renew", "send_command"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
