import unittest

from application.charge_lifecycle import ChargeLifecycleSnapshot, DeltaState, HoldState, SafetyState
from application.operator_timeline import CanonicalOperatorTimeline
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


def lifecycle(session="s-1", trace="t-1", phase="MIX"):
    return ChargeLifecycleSnapshot(session, "battery", "program", phase, 10.0, (), DeltaState("ACTIVE"), HoldState("IDLE"), SafetyState("NORMAL"), 20.0, trace)


def event(number, kind, session="s-1", trace="t-1", phase="MIX"):
    return CanonicalChargeEvent(str(number), float(number), session, trace, EventSource.DOMAIN, kind, phase_before=phase, phase_after=phase, reason="observed", metadata={"condition": "evidence"})


class OperatorTimelineCanonicalTests(unittest.TestCase):
    def test_active_session_uses_only_canonical_events(self):
        timeline = CanonicalOperatorTimeline.from_sources(lifecycle(), (event(1, EventType.SESSION_STARTED), event(2, EventType.DELTA_STARTED), event(3, EventType.HOLD_STARTED), event(4, EventType.SESSION_STOPPED), event(5, EventType.SESSION_STARTED, "old", "old-trace")))
        self.assertEqual(timeline.status, "READY")
        self.assertEqual(len(timeline.events), 4)
        self.assertEqual(timeline.graph_session_id, "s-1")

    def test_restored_session_preserves_identity_and_trace(self):
        timeline = CanonicalOperatorTimeline.from_sources(lifecycle("restored", "trace-restored"), (event(1, EventType.PHASE_STARTED, "restored", "trace-restored"),))
        self.assertEqual(timeline.session_id, "restored")
        self.assertEqual(timeline.events[0].trace_id, "trace-restored")

    def test_ambiguous_or_missing_events_are_unknown(self):
        timeline = CanonicalOperatorTimeline.from_sources(lifecycle(), (event(1, EventType.SESSION_STARTED, "other", "other-trace"),))
        self.assertEqual(timeline.status, "UNKNOWN")
        self.assertEqual(timeline.events, ())

    def test_event_display_contains_required_fields(self):
        item = CanonicalOperatorTimeline.from_sources(lifecycle(), (event(1, EventType.PHASE_TRANSITION),)).events[0]
        self.assertEqual((item.timestamp, item.phase, item.reason, item.condition), (1.0, "MIX", "observed", "evidence"))

    def test_new_session_resets_graph_identity(self):
        first = CanonicalOperatorTimeline.from_sources(lifecycle("one", "t1"), ())
        second = CanonicalOperatorTimeline.from_sources(lifecycle("two", "t2"), ())
        self.assertNotEqual(first.graph_session_id, second.graph_session_id)


if __name__ == "__main__":
    unittest.main()
