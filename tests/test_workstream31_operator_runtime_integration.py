import ast
import unittest
from pathlib import Path

from application.active_session_parity import ActiveSessionParityObserver
from application.operator_runtime_view import OperatorRuntimeViewComposer
from v3_core.canonical_events import CanonicalChargeEvent, CanonicalTimelineSnapshot, EventSource, EventType


class Workstream31OperatorRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        observer = ActiveSessionParityObserver()
        self.observation = observer.ingest(
            persisted={"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}},
            telemetry={"voltage": 17.14, "current": 3.48, "temperature": 35.0, "source": "HA+ESP"},
            rd={"phase": "mix"}, esphome={"output": True}, ha={"available": True},
        )
        self.parity = observer.compare(self.observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})

    def test_live_state_rendering_and_control_disabled(self):
        view = OperatorRuntimeViewComposer().compose(observation=self.observation, parity=self.parity)
        self.assertEqual("OBSERVE", view.mode)
        self.assertFalse(view.control_enabled)
        self.assertEqual(("Baic72", "mix", "active"), (view.profile, view.phase, view.state))
        self.assertAlmostEqual(59.6472, view.power, places=3)

    def test_timeline_is_current_session_only(self):
        timeline = CanonicalTimelineSnapshot("", "mix", "active", ())
        view = OperatorRuntimeViewComposer().compose(observation=self.observation, parity=self.parity, timeline=timeline)
        self.assertIsNone(view.timeline)
        no_identity = OperatorRuntimeViewComposer().compose(observation=self.observation, parity=self.parity, shadow={"lease": {"armed": True}, "evidence_freshness": 2.0})
        self.assertEqual("LEGACY_NO_IDENTITY", no_identity.identity_status)

    def test_timeline_and_diagnostics_are_rendered(self):
        event = CanonicalChargeEvent("e1", 1, "", "", EventSource.MANUAL, EventType.PHASE_TRANSITION)
        timeline = CanonicalTimelineSnapshot(None or "", "mix", "active", (event,))
        # A legacy session has no identity, so the view must not attach an unscoped timeline.
        view = OperatorRuntimeViewComposer().compose(observation=self.observation, parity=self.parity, timeline=timeline, diagnostics=({"severity": "warning", "message": "stale HA"}, {"severity": "error", "message": "unknown safety"}), shadow={"stale_sources": ("HA",)})
        self.assertEqual(("stale HA",), view.diagnostics.warnings)
        self.assertEqual(("unknown safety",), view.diagnostics.blockers)
        self.assertEqual(("HA",), view.diagnostics.stale_sources)
        self.assertIsNone(view.timeline)

    def test_matching_timeline_is_attached(self):
        observer = ActiveSessionParityObserver()
        observation = observer.ingest(persisted={"state": "active", "stage": "mix", "session_identity": {"session_id": "s1", "trace_id": "t1"}}, telemetry={"voltage": 17.14})
        parity = observer.compare(observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})
        timeline = CanonicalTimelineSnapshot("s1", "mix", "active", ())
        view = OperatorRuntimeViewComposer().compose(observation=observation, parity=parity, timeline=timeline)
        self.assertIs(view.timeline, timeline)

    def test_no_command_or_physical_path(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "operator_runtime_view.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("output_on", "output_off", "turn_on", "turn_off", "controller.start", "controller.stop", "lease_renew", "send_command"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
