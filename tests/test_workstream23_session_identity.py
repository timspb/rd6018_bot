import ast
import unittest
from pathlib import Path

from application.session_identity import CurrentSessionTimelineProvider, EventBucket, EventCorrelationResolver, SessionIdentityModel, TimelineReconstructor, TimelineStatus
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


ROOT = Path(__file__).resolve().parents[1]


def event(event_id, timestamp, kind, session="s", trace="t", phase_after=None):
    return CanonicalChargeEvent(event_id, timestamp, session, trace, EventSource.JOURNAL, kind, phase_after=phase_after, metadata={"telemetry_ref": event_id})


def complete_events(session="s"):
    kinds = (EventType.SESSION_STARTED, EventType.PHASE_STARTED, EventType.PHASE_TRANSITION, EventType.DELTA_STARTED, EventType.DELTA_COMPLETED, EventType.HOLD_STARTED, EventType.HOLD_COMPLETED, EventType.TERMINATION_DETECTED, EventType.SESSION_STOPPED)
    return tuple(event(str(index), float(index), kind, session=session, phase_after="mix" if kind is EventType.PHASE_TRANSITION else None) for index, kind in enumerate(kinds, 1))


class Workstream23SessionIdentityTests(unittest.TestCase):
    def test_new_restore_and_resume_identity(self):
        new = SessionIdentityModel.create(session_id="new", created_at=1, source="START", profile="Baic72", initial_phase="main")
        restored = SessionIdentityModel.create(session_id="restore", created_at=2, source="persisted", profile="Baic72", initial_phase="mix", restored=True)
        resumed = SessionIdentityModel.create(session_id="resume", created_at=3, source="operator", profile="Baic72", initial_phase="mix", resumed=True)
        self.assertFalse(new.restored)
        self.assertTrue(restored.restored)
        self.assertTrue(resumed.resumed)

    def test_historical_and_duplicate_start_are_isolated(self):
        session = SessionIdentityModel.create(session_id="current", created_at=10, source="START", profile="Baic72", initial_phase="main")
        events = (event("old", 1, EventType.SESSION_STARTED, session="old"), event("current", 11, EventType.SESSION_STARTED, session="current"), event("duplicate", 12, EventType.SESSION_STARTED, session="current"))
        result = TimelineReconstructor().rebuild(events, session)
        self.assertEqual(1, len(result.historical_events))
        self.assertEqual(2, len(result.current_events))
        self.assertNotIn(result.historical_events[0], result.current_events)

    def test_ambiguous_cross_session_event_is_not_guessed(self):
        session = SessionIdentityModel.create(session_id="current", created_at=10, source="START", profile="Baic72", initial_phase="main")
        classified = EventCorrelationResolver().classify(event("x", 11, EventType.PHASE_STARTED, session="other"), session, telemetry_timestamps=(11,))
        self.assertEqual(EventBucket.AMBIGUOUS, classified.bucket)
        self.assertEqual(TimelineStatus.AMBIGUOUS, TimelineReconstructor().rebuild((classified.event,), session, telemetry_timestamps=(11,)).status)

    def test_complete_reconstruction_and_ui_isolation(self):
        session = SessionIdentityModel.create(session_id="s", created_at=1, source="START", profile="Baic72", initial_phase="main")
        result = TimelineReconstructor().rebuild(complete_events(), session, current_phase="mix")
        self.assertEqual(TimelineStatus.COMPLETE, result.status)
        ui = CurrentSessionTimelineProvider().build(result)
        self.assertTrue(ui.graph_reset)
        self.assertFalse(ui.historical_events_included)

    def test_no_runtime_or_physical_imports(self):
        source = (ROOT / "application" / "session_identity.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "requests", "serial"})
        for token in ("controller.start", "controller.stop", "output_on", "output_off", "lease_renew"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
