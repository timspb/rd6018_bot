import ast
import unittest
from pathlib import Path

from application.session_birth_observation import BirthStatus, LiveSessionBirthObserver, SessionBirthTimelineGuard
from application.session_identity import CurrentSessionTimeline


ROOT = Path(__file__).resolve().parents[1]


class Workstream24SessionBirthTests(unittest.TestCase):
    def test_idle_to_active_birth_is_captured(self):
        evidence = LiveSessionBirthObserver().observe(
            before={"timestamp": 1, "active": False},
            after={"timestamp": 2, "active": True, "session_id": "s1", "profile": "Baic72", "phase": "main"},
            start_event={"timestamp": 2, "session_id": "s1", "trace_id": "t1", "source": "V2"},
        )
        self.assertEqual(BirthStatus.CAPTURED, evidence.status)
        self.assertEqual("s1", evidence.session.session_id)

    def test_current_active_state_does_not_fake_birth(self):
        evidence = LiveSessionBirthObserver().observe(before={"timestamp": 1, "active": True}, after={"timestamp": 2, "active": True, "profile": "Baic72", "phase": "mix"})
        self.assertEqual(BirthStatus.NOT_OBSERVED, evidence.status)

    def test_missing_identity_is_blocked(self):
        evidence = LiveSessionBirthObserver().observe(before={"active": False}, after={"timestamp": 2, "active": True, "profile": "Baic72", "phase": "main"}, start_event={"timestamp": 2})
        self.assertEqual(BirthStatus.BLOCKED, evidence.status)
        self.assertIn("session_id", evidence.missing_fields)
        self.assertIn("trace_id", evidence.missing_fields)

    def test_timeline_is_bound_to_birth_and_reset(self):
        evidence = LiveSessionBirthObserver().observe(before={"active": False}, after={"timestamp": 2, "active": True, "session_id": "s1", "profile": "Baic72", "phase": "main"}, start_event={"timestamp": 2, "session_id": "s1", "trace_id": "t1"})
        timeline = CurrentSessionTimeline("s1", (), True, False)
        self.assertTrue(SessionBirthTimelineGuard().accept(evidence, timeline))

    def test_no_runtime_or_write_imports(self):
        source = (ROOT / "application" / "session_birth_observation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "requests", "serial"})
        for token in ("controller.start", "controller.stop", "output_on", "output_off", "lease_renew"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
