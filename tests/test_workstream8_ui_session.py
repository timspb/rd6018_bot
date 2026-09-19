import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from v3_core.ui_session import (
    ChargeTimelineEvent,
    GraphSample,
    OperatorTimelineFormatter,
    SessionState,
    SessionTimeline,
    TimelineEventType,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream8UISessionTests(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime.now(timezone.utc)

    def test_start_creates_new_session_and_clears_presentation_state(self):
        timeline = SessionTimeline()
        first = timeline.start(started_at=self.t0)
        timeline.add(TimelineEventType.PHASE_CHANGED, timestamp=self.t0 + timedelta(seconds=1), payload={"to": "CV"})
        second = timeline.start(started_at=self.t0 + timedelta(hours=1))
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(1, len(timeline.events))
        self.assertEqual(second.session_id, timeline.graph.session_id)
        self.assertEqual(0, len(timeline.graph.samples))

    def test_phase_transition_creates_timeline_event(self):
        timeline = SessionTimeline()
        session = timeline.start(started_at=self.t0)
        event = timeline.add(TimelineEventType.PHASE_CHANGED, timestamp=self.t0 + timedelta(seconds=2), payload={"from": "BULK", "to": "ABSORPTION"})
        self.assertEqual(session.session_id, event.session_id)
        self.assertEqual("ABSORPTION", event.payload["to"])

    def test_delta_and_hold_events_are_visible(self):
        timeline = SessionTimeline()
        timeline.start(started_at=self.t0)
        for event_type in (TimelineEventType.DELTA_STARTED, TimelineEventType.DELTA_COMPLETED, TimelineEventType.HOLD_STARTED, TimelineEventType.HOLD_COMPLETED):
            timeline.add(event_type, timestamp=self.t0 + timedelta(seconds=len(timeline.events)), payload={"value": 1})
        formatted = OperatorTimelineFormatter().format(timeline.events)
        self.assertEqual(5, len(formatted))

    def test_stop_closes_session(self):
        timeline = SessionTimeline()
        timeline.start(started_at=self.t0)
        timeline.stop(timestamp=self.t0 + timedelta(seconds=10))
        self.assertEqual(SessionState.COMPLETED, timeline.session.current_state)
        self.assertEqual(TimelineEventType.SESSION_STOPPED, timeline.events[-1].event_type)

    def test_failed_stop_is_explicit_not_empty_state(self):
        timeline = SessionTimeline()
        timeline.start(started_at=self.t0)
        timeline.stop(timestamp=self.t0 + timedelta(seconds=1), failed=True)
        self.assertEqual(SessionState.FAILED, timeline.session.current_state)
        self.assertNotEqual("", timeline.events[-1].payload["state"])

    def test_graph_is_session_scoped_and_old_samples_are_invisible(self):
        timeline = SessionTimeline()
        first = timeline.start(started_at=self.t0)
        timeline.graph = timeline.graph.append(GraphSample(1, 14.7, 2, 29.4, 23))
        second = timeline.start(started_at=self.t0 + timedelta(hours=1))
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(0, len(timeline.graph.samples))

    def test_timeline_ordering_is_timestamp_then_sequence(self):
        timeline = SessionTimeline()
        timeline.start(started_at=self.t0)
        late = timeline.add(TimelineEventType.PHASE_CHANGED, timestamp=self.t0 + timedelta(seconds=2))
        early = ChargeTimelineEvent(timeline.session.session_id, TimelineEventType.HOLD_STARTED, self.t0 + timedelta(seconds=1), 99)
        result = OperatorTimelineFormatter().format((late, early))
        self.assertEqual(early, result[0])

    def test_ui_module_has_no_domain_runtime_or_execution_imports(self):
        path = ROOT / "v3_core" / "ui_session.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not any(token in item for token in ("runtime", "application", "hass", "esphome", "execution")) for item in imports))

    def test_ui_module_has_no_physical_calls(self):
        text = (ROOT / "v3_core" / "ui_session.py").read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current(", "dispatch("):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
