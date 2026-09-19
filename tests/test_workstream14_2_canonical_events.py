import ast
import unittest
from pathlib import Path

from v3_core.canonical_events import (
    CanonicalTimelineSnapshot,
    EventActivity,
    EventNormalizer,
    EventSource,
    EventType,
    build_timeline,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream142CanonicalEventsTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = EventNormalizer()

    def test_main_to_mix_is_phase_transition_not_session_stop(self):
        event = self.normalizer.normalize({"event_type": "MANUAL_TRANSITION", "old": "stopped", "new": "cooling", "reason": "manual_main_to_mix_prepare", "timestamp": 2}, source=EventSource.JOURNAL, session_id="s", trace_id="t", event_id="2")
        self.assertEqual(EventType.PHASE_TRANSITION, event.event_type)

    def test_session_stop_is_distinct(self):
        event = self.normalizer.normalize({"event_type": "STOP", "reason": "operator_stop", "timestamp": 1}, source=EventSource.MANUAL, session_id="s", trace_id="t", event_id="1")
        self.assertEqual(EventType.SESSION_STOPPED, event.event_type)

    def test_delta_hold_and_historical_emergency(self):
        delta = self.normalizer.normalize({"event_type": "DELTA_START"}, source=EventSource.JOURNAL, session_id="s", trace_id="t", event_id="1")
        hold = self.normalizer.normalize({"event_type": "HOLD_COMPLETED"}, source=EventSource.JOURNAL, session_id="s", trace_id="t", event_id="2")
        emergency = self.normalizer.normalize({"event_type": "EMERGENCY_UNAVAILABLE"}, source=EventSource.LEGACY_HISTORY, session_id="s", trace_id="t", event_id="3")
        self.assertEqual(EventType.DELTA_STARTED, delta.event_type)
        self.assertEqual(EventType.HOLD_COMPLETED, hold.event_type)
        self.assertEqual((EventType.FAULT_DETECTED, EventActivity.HISTORICAL), (emergency.event_type, emergency.activity))

    def test_ordering_and_session_filter(self):
        events = tuple(self.normalizer.normalize({"event_type": "START", "timestamp": value}, source=EventSource.JOURNAL, session_id=session, trace_id="t", event_id=str(value)) for value, session in ((3, "s"), (1, "s"), (2, "other")))
        timeline = build_timeline(events, session_id="s", current_phase="mix", current_state="active")
        self.assertIsInstance(timeline, CanonicalTimelineSnapshot)
        self.assertEqual(("1", "3"), tuple(item.event_id for item in timeline.ordered_events))

    def test_ui_contract_is_canonical_snapshot_only(self):
        timeline = build_timeline((), session_id="s", current_phase="mix", current_state="active")
        self.assertEqual("s", timeline.session_id)
        self.assertFalse(hasattr(timeline, "journal"))
        self.assertFalse(hasattr(timeline, "history_log"))

    def test_no_source_or_physical_side_effect_imports(self):
        source = (ROOT / "v3_core" / "canonical_events.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        forbidden = {"aiohttp", "paramiko", "esphome", "serial", "requests"}
        self.assertFalse(imports & forbidden)
        self.assertNotIn("output_on", source)
        self.assertNotIn("set_voltage", source)


if __name__ == "__main__":
    unittest.main()
