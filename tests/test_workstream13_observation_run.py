import ast
import unittest
from pathlib import Path

from v3_core.hardware_validation import RealObservation, compare_shadow_observation
from v3_core.observation_run import LiveShadowObservationRun, ObservationRunStatus, ObservationSession, UiObservation


ROOT = Path(__file__).resolve().parents[1]


class Workstream13ObservationRunTests(unittest.TestCase):
    def test_lifecycle_and_evidence_integrity(self):
        session = ObservationSession("obs-1", 1.0, None, "V2", "READ_ONLY", {"HA": True, "ESPHome": False}, ObservationRunStatus.OPEN)
        run = LiveShadowObservationRun(session)
        run.add_telemetry(RealObservation("HA", 2.0, 1.0, 1.0, True, {"voltage": 14.8}))
        run.add_timeline_event({"event": "START", "trace_id": "t1"})
        run.add_divergence(compare_shadow_observation({"phase": "CV"}, {"phase": "CV"}))
        run.set_ui_observation(UiObservation(True, True, True, True, True))
        bundle = run.close(3.0)
        self.assertEqual(ObservationRunStatus.CLOSED, bundle.metadata.status)
        self.assertEqual("V2", bundle.metadata.v2_owner)
        self.assertEqual("t1", bundle.timeline[0]["trace_id"])
        self.assertTrue(bundle.ui_observation.session_starts_from_zero)

    def test_blocked_run_preserves_source_availability(self):
        session = ObservationSession("obs-2", 1.0, None, "V2", "READ_ONLY", {"HA": False}, ObservationRunStatus.OPEN)
        bundle = LiveShadowObservationRun(session).close(2.0, blocked=True)
        self.assertEqual(ObservationRunStatus.BLOCKED, bundle.metadata.status)
        self.assertFalse(bundle.metadata.source_availability["HA"])

    def test_no_control_or_external_write_symbols(self):
        source = (ROOT / "v3_core" / "observation_run.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"set_voltage", "set_current", "output_on", "output_off", "turn_on", "turn_off", "write", "requests", "aiohttp"}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(forbidden & (names | attrs))


if __name__ == "__main__":
    unittest.main()
