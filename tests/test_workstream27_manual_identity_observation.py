import unittest

from application.manual_identity_runtime_observation import (
    ManualIdentityObservationStatus,
    ManualIdentityRuntimeObserver,
)
from application.manual_session_identity_contract import ManualSessionEvent, ManualSessionEventBridge, ManualSessionIdentityBoundaryContract


class Workstream27ManualIdentityObservationTests(unittest.TestCase):
    def setUp(self):
        self.observer = ManualIdentityRuntimeObserver()

    def test_start_identity_is_observed_but_not_created_by_observer(self):
        result = self.observer.observe_start(
            before={"state": "idle"},
            after={"state": "active", "profile": "Baic72", "graph_reset": True},
            start_event={"session_id": "s1", "trace_id": "t1", "timestamp": 10, "source": "V2"},
        )
        self.assertEqual(ManualIdentityObservationStatus.VALIDATED, result.status)
        self.assertEqual(("s1", "t1"), (result.session_id, result.trace_id))

    def test_missing_runtime_identity_blocks(self):
        result = self.observer.observe_start(before={"state": "idle"}, after={"state": "active", "profile": "Baic72"}, start_event={"timestamp": 10, "source": "V2"})
        self.assertEqual(ManualIdentityObservationStatus.BLOCKED, result.status)
        self.assertIn("session_id", result.missing_fields)
        self.assertIn("trace_id", result.missing_fields)

    def test_event_trace_and_session_must_be_consistent(self):
        contract = ManualSessionIdentityBoundaryContract()
        identity = contract.new_start(session_id="s1", trace_id="t1", created_at=10, source="V2", profile="Baic72")
        event = ManualSessionEventBridge().to_canonical(ManualSessionEvent("SessionStarted", 10, identity), event_id="e1")
        result = self.observer.capture_bundle(events=(event,), ui_timeline_valid=True)
        self.assertEqual(ManualIdentityObservationStatus.VALIDATED, result.status)
        self.assertEqual(("s1", "t1"), (result.session_id, result.trace_id))

    def test_empty_chain_blocks(self):
        result = self.observer.capture_bundle(events=())
        self.assertEqual(ManualIdentityObservationStatus.BLOCKED, result.status)
        self.assertIn("events", result.missing_fields)

    def test_legacy_restore_remains_ambiguous(self):
        self.assertEqual("AMBIGUOUS", self.observer.classify_legacy_restore({"state": "active", "started_at": 10}, now=20))

    def test_ui_reset_is_required_for_valid_bundle(self):
        contract = ManualSessionIdentityBoundaryContract()
        identity = contract.new_start(session_id="s1", trace_id="t1", created_at=10, source="V2", profile="Baic72")
        event = ManualSessionEventBridge().to_canonical(ManualSessionEvent("SessionStarted", 10, identity), event_id="e1")
        result = self.observer.capture_bundle(events=(event,), ui_timeline_valid=False)
        self.assertEqual(ManualIdentityObservationStatus.BLOCKED, result.status)
        self.assertIn("ui_timeline", result.missing_fields)


if __name__ == "__main__":
    unittest.main()
