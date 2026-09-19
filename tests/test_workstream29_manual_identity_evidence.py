import ast
import unittest
from pathlib import Path

from application.manual_identity_evidence import ManualIdentityEvidenceCollector, ManualIdentityEvidenceStatus
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


def event(event_type, timestamp, *, session="s1", trace="t1", metadata=None):
    return CanonicalChargeEvent(f"e-{timestamp}", timestamp, session, trace, EventSource.MANUAL, event_type, metadata=metadata or {"telemetry_ref": f"tel-{timestamp}"})


class Workstream29ManualIdentityEvidenceTests(unittest.TestCase):
    def test_partial_capture_is_not_promoted_to_complete(self):
        result = ManualIdentityEvidenceCollector().capture(events=(event(EventType.SESSION_STARTED, 1),), session_id="s1")
        self.assertEqual(ManualIdentityEvidenceStatus.PARTIAL, result.status)
        self.assertFalse(result.chain_result.complete)

    def test_complete_chain_replays_without_execution(self):
        chain = (
            event(EventType.SESSION_STARTED, 1),
            event(EventType.PHASE_STARTED, 2),
            event(EventType.PHASE_TRANSITION, 3),
            event(EventType.DELTA_STARTED, 4),
            event(EventType.DELTA_COMPLETED, 5),
            event(EventType.HOLD_STARTED, 6),
            event(EventType.HOLD_COMPLETED, 7),
            event(EventType.TERMINATION_DETECTED, 8),
            event(EventType.SESSION_STOPPED, 9),
        )
        result = ManualIdentityEvidenceCollector().capture(events=chain, session_id="s1", ui_timeline_valid=True)
        self.assertEqual(ManualIdentityEvidenceStatus.CAPTURED, result.status)
        self.assertIsNotNone(result.replay_result)
        self.assertFalse(result.replay_result.execution_performed)

    def test_ui_invalidates_capture(self):
        result = ManualIdentityEvidenceCollector().capture(events=(event(EventType.SESSION_STARTED, 1),), session_id="s1", ui_timeline_valid=False)
        self.assertEqual(ManualIdentityEvidenceStatus.PARTIAL, result.status)

    def test_missing_identity_blocks(self):
        result = ManualIdentityEvidenceCollector().capture(events=(), session_id=None)
        self.assertEqual(ManualIdentityEvidenceStatus.BLOCKED, result.status)

    def test_no_source_clients_or_physical_calls(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "manual_identity_evidence.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("output_on", "output_off", "turn_on", "turn_off", "lease_renew", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
