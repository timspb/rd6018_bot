import unittest

from application.operator_graph import GraphRange, GraphSample
from application.operator_panel import ControlsState, OperatorPanelState, TelegramOperatorPanelFormatter
from application.operator_state import CCVState, OperatorStateSnapshot, PhaseLifecycleState, SafetyView, TelemetryView
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


def snapshot(session="s77", trace="t77", phase="MIX"):
    return OperatorStateSnapshot(
        "Baic72", "Baic72", "CALCIUM", "MANUAL", "manual:Baic72", phase,
        PhaseLifecycleState.ACTIVE, ("Delta complete",), 17.5, 3.5, ("hold",),
        TelemetryView(17.1, 3.49, 59.7, 36.0, CCVState.CC, 100.0, "FRESH"),
        SafetyView("OK", "FRESH", "HIGH"), "ACTIVE", session, trace,
        "phase explanation", ("termination criteria",), "HOLD",
    )


def sample(session, timestamp=100.0):
    return GraphSample(timestamp, session, 17.1, 3.49, 36.0, True)


def event(event_id, session, trace, event_type):
    return CanonicalChargeEvent(
        event_id, 100.0, session, trace, EventSource.DOMAIN, event_type,
        phase_before="MIX", phase_after="MIX", reason="observed",
        metadata={"condition": "evidence"},
    )


class OperatorPanelIntegrityTests(unittest.TestCase):
    def test_single_snapshot_composes_all_panel_parts(self):
        diagnostics = object()
        panel = OperatorPanelState.compose(
            snapshot(), samples=(sample("s77"),),
            events=(event("e1", "s77", "t77", EventType.PHASE_STARTED),),
            selected_range=GraphRange.SESSION,
            diagnostics_reference=diagnostics,
        )
        self.assertIsInstance(panel, OperatorPanelState)
        self.assertIs(panel.diagnostics_reference, diagnostics)
        self.assertEqual(panel.card.phase, panel.graphs.session_id and "MIX")
        self.assertEqual(panel.log.session_id, panel.graphs.session_id)
        self.assertIsInstance(panel.controls, ControlsState)

    def test_new_session_resets_graph_and_filters_log(self):
        panel = OperatorPanelState.compose(
            snapshot(session="new", trace="new-trace"),
            samples=(sample("old"), sample("new")),
            events=(
                event("old", "old", "old-trace", EventType.SESSION_STARTED),
                event("new", "new", "new-trace", EventType.SESSION_STARTED),
            ),
            selected_range=GraphRange.SESSION,
        )
        self.assertEqual(len(panel.graphs.voltage.points), 1)
        self.assertEqual(panel.log.session_id, "new")
        self.assertEqual(len(panel.log.events), 1)
        self.assertEqual(panel.log.events[0].event, "SessionStarted")

    def test_unknown_session_is_explicit_and_degraded(self):
        panel = OperatorPanelState.compose(
            snapshot(session=None, trace=None), samples=(sample("legacy"),), events=(),
        )
        self.assertEqual(panel.graphs.status, "AMBIGUOUS_SESSION")
        self.assertEqual(panel.log.status, "AMBIGUOUS_SESSION")
        self.assertIn("UNKNOWN", panel.log.format())

    def test_controls_are_presentation_only(self):
        panel = OperatorPanelState.compose(snapshot())
        self.assertTrue(panel.observe_only)
        self.assertTrue(panel.controls.presentation_only)
        self.assertTrue(all(button.presentation_only for button in panel.action_buttons))
        self.assertEqual(panel.controls.selected_range, GraphRange.THIRTY_MINUTES)

    def test_formatter_uses_panel_only_and_keeps_diagnostics_separate(self):
        panel = OperatorPanelState.compose(snapshot(), diagnostics_reference={"warnings": ("hidden",)})
        rendered = TelegramOperatorPanelFormatter().format(panel)
        self.assertIn("Baic72", rendered)
        self.assertNotIn("hidden", rendered)
        self.assertNotIn("diagnostic", rendered.lower())

    def test_panel_modules_have_no_runtime_or_physical_dependencies(self):
        for module_name in ("application.operator_panel", "application.operator_graph", "application.operator_controls", "application.operator_log"):
            module = __import__(module_name, fromlist=["*"])
            with open(module.__file__, encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("ChargeController", "HassClient", "ESPHome", "PhysicalExecution", "turn_on", "turn_off"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
