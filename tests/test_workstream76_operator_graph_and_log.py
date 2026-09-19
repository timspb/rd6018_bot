import unittest

from application.operator_controls import OperatorPresentationState
from application.operator_graph import GraphRange, GraphSample, GraphViewModel
from application.operator_log import OperatorLogViewModel
from application.operator_panel import OperatorPanelViewModel, TelegramOperatorPanelFormatter
from application.operator_state import CCVState, OperatorStateSnapshot, PhaseLifecycleState, SafetyView, TelemetryView
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


def state(phase="MIX", mode="MANUAL", session="s76", trace="t76"):
    return OperatorStateSnapshot(
        "Baic72", "Baic72", "CALCIUM", mode, "manual:Baic72", phase,
        PhaseLifecycleState.ACTIVE, ("Delta complete",), 17.5, 3.5, ("hold",),
        TelemetryView(17.1, 3.49, 59.7, 36.0, CCVState.CC, 100.0, "FRESH"),
        SafetyView("OK", "FRESH", "HIGH"), "ACTIVE", session, trace,
        "phase explanation", ("termination criteria",), "HOLD",
    )


def samples(session="s76"):
    return tuple(GraphSample(ts, session, 14.0 + ts / 1000, 3.0, 30.0, True) for ts in (100, 500, 2000, 8000))


def event(event_id, timestamp, event_type, session="s76", trace="t76", phase="MIX", reason="observed"):
    return CanonicalChargeEvent(event_id, timestamp, session, trace, EventSource.DOMAIN, event_type, phase_before=phase, phase_after=phase, reason=reason, metadata={"condition": "evidence"})


class OperatorGraphLogTests(unittest.TestCase):
    def test_graph_series_and_range_filtering(self):
        graph = GraphViewModel.from_samples(samples(), session_id="s76", selected_range=GraphRange.TWO_HOURS, now=8000)
        self.assertEqual(len(graph.voltage.points), 2)
        self.assertEqual(len(graph.current.points), 2)
        self.assertEqual(len(graph.battery_temperature.points), 2)

    def test_graph_reset_and_no_cross_session_leakage(self):
        graph = GraphViewModel.from_samples(samples("old") + samples("new"), session_id="new", selected_range=GraphRange.SESSION)
        self.assertEqual(graph.session_id, "new")
        self.assertTrue(all(point.timestamp in (100, 500, 2000, 8000) for point in graph.voltage.points))
        self.assertEqual(len(graph.voltage.points), 4)
        empty = GraphViewModel.from_samples(samples("old"), session_id="new", selected_range=GraphRange.SESSION)
        self.assertEqual(empty.status, "EMPTY_OR_DEGRADED")
        self.assertEqual(empty.voltage.points, ())

    def test_controls_are_ui_state_and_log_selection_is_separate(self):
        presentation = OperatorPresentationState().select_range(GraphRange.LOG)
        self.assertEqual(presentation.selected_range, GraphRange.LOG)
        panel = OperatorPanelViewModel.compose(state(), samples=samples(), events=(), selected_range=GraphRange.SESSION)
        self.assertTrue(panel.observe_only)
        self.assertEqual([button.label for button in panel.range_buttons], ["30м", "2ч", "Сессия", "Лог"])
        self.assertEqual([button.label for button in panel.action_buttons], ["Пауза", "Стоп", "Обновить"])
        self.assertTrue(all(button.presentation_only for button in panel.action_buttons))

    def test_log_is_current_session_only_and_normalized(self):
        events = (event("1", 100, EventType.SESSION_STARTED), event("2", 200, EventType.DELTA_STARTED), event("3", 300, EventType.HOLD_STARTED), event("old", 400, EventType.SESSION_STOPPED, session="old", trace="old"))
        log = OperatorLogViewModel.from_events(events, session_id="s76", trace_id="t76")
        self.assertEqual(len(log.events), 3)
        self.assertIn("DeltaStarted", log.format())
        self.assertNotIn("SessionStopped", log.format())

    def test_ambiguous_and_missing_logs_are_explicit(self):
        log = OperatorLogViewModel.from_events((), session_id="UNKNOWN")
        self.assertEqual(log.status, "AMBIGUOUS_SESSION")
        self.assertIn("UNKNOWN", log.format())

    def test_main_panel_layout_and_diagnostics_separation(self):
        panel = OperatorPanelViewModel.compose(state("MAIN", "AUTO"), samples=samples(), events=(event("1", 100, EventType.PHASE_STARTED, phase="MAIN"),), selected_range=GraphRange.THIRTY_MINUTES)
        text = TelegramOperatorPanelFormatter().format(panel)
        self.assertLess(text.index("📈 Voltage"), text.index("🔋 Baic72"))
        self.assertIn("30м · 2ч · Сессия · Лог", text)
        self.assertIn("Пауза · Стоп · Обновить", text)
        self.assertIn("CC", text)
        self.assertIn("AUTO", text)
        self.assertNotIn("RD6018", text)
        self.assertNotIn("ЗАРЯД", text)
        self.assertNotIn("warnings", text.lower())
        self.assertNotIn("blockers", text.lower())

    def test_no_runtime_or_physical_imports(self):
        for module_name in ("application.operator_graph", "application.operator_controls", "application.operator_log", "application.operator_panel"):
            module = __import__(module_name, fromlist=["*"])
            with open(module.__file__, encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("ChargeController", "HassClient", "ESPHome", "PhysicalExecution", "turn_on", "turn_off"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
