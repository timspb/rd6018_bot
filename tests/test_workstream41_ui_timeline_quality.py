import unittest
from datetime import datetime, timedelta, timezone

from v3_core.ui_session import (
    GraphSample,
    OperatorTimelineFormatter,
    SessionTimeline,
    TimelineEventType,
)


class Workstream41UITimelineQualityTests(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_new_session_resets_graph_origin_and_old_points(self):
        timeline = SessionTimeline()
        first = timeline.start(started_at=self.t0, phase="MAIN")
        timeline.graph = timeline.graph.append(GraphSample(1.0, 14.0, 2.0, 28.0, 23.0))
        second = timeline.start(started_at=self.t0 + timedelta(hours=1), phase="MIX")
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(second.session_id, timeline.graph.session_id)
        self.assertEqual((), timeline.graph.samples)
        self.assertEqual(0.0, second.elapsed_time_s)

    def test_current_session_filter_excludes_historical_events(self):
        timeline = SessionTimeline()
        first = timeline.start(started_at=self.t0)
        timeline.add(TimelineEventType.PHASE_CHANGED, timestamp=self.t0 + timedelta(seconds=1), payload={"to": "CV"})
        first_events = timeline.events
        second = timeline.start(started_at=self.t0 + timedelta(hours=1), phase="MIX")
        timeline.add(TimelineEventType.DELTA_COMPLETED, timestamp=self.t0 + timedelta(hours=1, seconds=2), payload={"reason": "Delta complete", "condition": "termination criteria"})
        display = OperatorTimelineFormatter().display(first_events + timeline.events, session_id=second.session_id)
        self.assertEqual("READY", display.status)
        self.assertEqual(2, len(display.events))
        self.assertTrue(all(event.event_time.startswith("2026-01-01T01:") for event in display.events))

    def test_phase_delta_and_hold_markers_are_explicit(self):
        timeline = SessionTimeline()
        session = timeline.start(started_at=self.t0, phase="MAIN")
        timeline.add(TimelineEventType.PHASE_CHANGED, timestamp=self.t0 + timedelta(seconds=1), payload={"to": "MIX", "reason": "Delta complete", "condition": "termination criteria"})
        timeline.add(TimelineEventType.DELTA_STARTED, timestamp=self.t0 + timedelta(seconds=2), payload={"phase": "MIX", "reason": "Delta start", "condition": "waiting for confirmation"})
        timeline.add(TimelineEventType.DELTA_COMPLETED, timestamp=self.t0 + timedelta(seconds=3), payload={"phase": "MIX", "reason": "Delta complete", "condition": "hold criteria"})
        timeline.add(TimelineEventType.HOLD_STARTED, timestamp=self.t0 + timedelta(seconds=4), payload={"phase": "MIX", "reason": "Hold start", "condition": "termination criteria"})
        display = OperatorTimelineFormatter().display(timeline.events, session_id=session.session_id)
        self.assertEqual(("MIX", "MIX", "MIX", "MIX"), tuple(event.phase for event in display.events[1:]))
        self.assertEqual("Delta complete", display.events[1].reason)
        self.assertEqual("termination criteria", display.events[1].condition)
        self.assertEqual("Delta complete", display.events[3].reason)

    def test_no_events_is_unknown_not_empty_text(self):
        display = OperatorTimelineFormatter().display((), session_id="s1")
        self.assertEqual("UNKNOWN", display.status)
        self.assertEqual((), display.events)

    def test_missing_reason_and_condition_are_explicit_unknown(self):
        timeline = SessionTimeline()
        session = timeline.start(started_at=self.t0, phase="MIX")
        timeline.add(TimelineEventType.HOLD_STARTED, timestamp=self.t0 + timedelta(seconds=1))
        display = OperatorTimelineFormatter().display(timeline.events, session_id=session.session_id)
        self.assertEqual("UNKNOWN", display.events[-1].reason)
        self.assertEqual("UNKNOWN", display.events[-1].condition)

    def test_quality_model_has_no_runtime_or_physical_imports(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "v3_core" / "ui_session.py").read_text(encoding="utf-8")
        for forbidden in ("aiohttp", "aioesphomeapi", "paramiko", "serial", "controller.start", "controller.stop"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
