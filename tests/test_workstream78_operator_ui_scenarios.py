import unittest

from application.operator_graph import GraphRange, GraphSample
from application.operator_panel import OperatorPanelState, TelegramOperatorPanelFormatter
from application.operator_state import CCVState, OperatorStateSnapshot, PhaseLifecycleState, SafetyView, TelemetryView
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


def snapshot(phase, mode="MANUAL", session="s78", trace="t78", telemetry=None, freshness="FRESH"):
    telemetry = telemetry or TelemetryView(17.1, 3.49, 59.7, 36.0, CCVState.CC, 100.0, freshness)
    return OperatorStateSnapshot(
        "Baic72", "Baic72", "CALCIUM", mode, "manual:Baic72", phase,
        PhaseLifecycleState.WAITING if phase == "SAFE_WAIT" else PhaseLifecycleState.ACTIVE,
        ("Delta complete",) if phase in ("MIX", "HOLD") else (),
        17.5, 3.5, ("hold",) if phase in ("MIX", "HOLD") else (), telemetry,
        SafetyView("OK" if phase != "SAFE_WAIT" else "WAITING", freshness, "HIGH"),
        "ACTIVE" if phase not in ("DONE",) else "DONE", session, trace,
        "phase explanation", ("termination criteria",), "HOLD" if phase == "MIX" else None,
    )


def event(event_id, event_type, session="s78", trace="t78", phase="MIX"):
    return CanonicalChargeEvent(
        event_id, 100.0, session, trace, EventSource.DOMAIN, event_type,
        phase_before=phase, phase_after=phase, reason="synthetic", metadata={"condition": "test"},
    )


def panel_for(state, *, with_event=True):
    return OperatorPanelState.compose(
        state,
        samples=(GraphSample(100.0, state.session_id or "legacy", 17.1, 3.49, 36.0, state.telemetry.freshness == "FRESH"),),
        events=(event("e1", EventType.PHASE_STARTED, state.session_id or "legacy", state.trace_id or "legacy", state.current_phase),) if with_event and state.session_id else (),
        selected_range=GraphRange.SESSION,
        diagnostics_reference={"warnings": ("separate",)},
    )


class OperatorUIScenarioTests(unittest.TestCase):
    def assert_card_basics(self, state, expected_mode, expected_phase):
        panel = panel_for(state)
        rendered = TelegramOperatorPanelFormatter().format(panel)
        self.assertIn("🔋 Baic72", rendered)
        self.assertIn(expected_phase, rendered)
        self.assertIn(expected_mode, rendered)
        self.assertIn("CC", rendered)
        self.assertNotIn("RD6018", rendered)
        self.assertNotIn("ЗАРЯД", rendered)
        return panel, rendered

    def test_manual_mix(self):
        panel, rendered = self.assert_card_basics(snapshot("MIX"), "MANUAL", "MIX")
        self.assertEqual(panel.graphs.status, "READY")
        self.assertEqual(panel.log.status, "READY")
        self.assertIn("Delta complete", rendered)

    def test_auto_main(self):
        panel, rendered = self.assert_card_basics(snapshot("MAIN", mode="AUTO"), "AUTO", "MAIN")
        self.assertEqual(panel.card.phase, "MAIN")
        self.assertIn("17.50 V", rendered)

    def test_hold_with_timer_and_safe_wait(self):
        hold = panel_for(snapshot("HOLD"), with_event=False)
        safe_wait = panel_for(snapshot("SAFE_WAIT"), with_event=False)
        self.assertIn("condition:", TelegramOperatorPanelFormatter().format(hold))
        self.assertIn("waiting:", TelegramOperatorPanelFormatter().format(safe_wait))

    def test_done(self):
        panel, rendered = self.assert_card_basics(snapshot("DONE"), "MANUAL", "DONE")
        self.assertEqual(panel.card.phase, "DONE")

    def test_legacy_session_without_identity_is_unknown(self):
        panel = panel_for(snapshot("MIX", session=None, trace=None))
        self.assertEqual(panel.graphs.status, "AMBIGUOUS_SESSION")
        self.assertEqual(panel.log.status, "AMBIGUOUS_SESSION")
        self.assertIn("UNKNOWN", panel.log.format())

    def test_missing_telemetry_is_visible(self):
        missing = TelemetryView(None, None, None, None, CCVState.UNKNOWN, None, "MISSING")
        panel = panel_for(snapshot("MAIN", telemetry=missing))
        rendered = TelegramOperatorPanelFormatter().format(panel)
        self.assertIn("UNKNOWN", rendered)
        self.assertEqual(panel.graphs.status, "EMPTY_OR_DEGRADED")

    def test_stale_source_does_not_create_graph_points(self):
        stale = TelemetryView(17.1, 3.49, 59.7, 36.0, CCVState.CV, 100.0, "STALE")
        panel = panel_for(snapshot("MIX", telemetry=stale))
        self.assertEqual(panel.graphs.status, "EMPTY_OR_DEGRADED")
        self.assertEqual(panel.graphs.voltage.points, ())

    def test_diagnostics_are_separate_and_no_side_effects(self):
        panel = panel_for(snapshot("MIX"))
        rendered = TelegramOperatorPanelFormatter().format(panel)
        self.assertNotIn("separate", rendered)
        self.assertTrue(panel.observe_only)
        self.assertTrue(all(button.presentation_only for button in panel.action_buttons))

    def test_scenario_modules_have_no_external_or_control_imports(self):
        for module_name in ("application.operator_panel", "application.operator_graph", "application.operator_controls", "application.operator_log"):
            module = __import__(module_name, fromlist=["*"])
            with open(module.__file__, encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("HassClient", "ESPHome", "Modbus", "turn_on", "turn_off", "ChargeController"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
