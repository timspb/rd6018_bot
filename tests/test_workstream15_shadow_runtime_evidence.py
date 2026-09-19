import ast
import unittest
from pathlib import Path

from v3_core.canonical_events import EventSource, EventNormalizer
from v3_core.hardware_validation import RealObservation, compare_shadow_observation
from v3_core.shadow_runtime_evidence import EvidenceCorrelationEngine, ExecutionObservation, ShadowEvidenceBundle, ShadowReplayEngine, ShadowRuntimeEvidenceNamespace

ROOT = Path(__file__).resolve().parents[1]


class Workstream15ShadowRuntimeEvidenceTests(unittest.TestCase):
    def bundle(self):
        n = EventNormalizer()
        events = (n.normalize({"event_type": "START", "timestamp": 1}, source=EventSource.JOURNAL, session_id="s", trace_id="t", event_id="1"), n.normalize({"event_type": "MANUAL_TRANSITION", "old": "main", "new": "mix", "timestamp": 2}, source=EventSource.JOURNAL, session_id="s", trace_id="t", event_id="2"))
        return ShadowEvidenceBundle("e", "o", "s", "t", 3, events=events, current_phase="mix", session_state="active", telemetry=(RealObservation("HA", 2, 1, 1, True, {"voltage": 16.5}),), execution_observations=(ExecutionObservation("SET_VOLTAGE", 2, "s", "t", "VERIFIED", "observed"),), divergences=(compare_shadow_observation({"phase": "mix"}, {"phase": "mix"}),))

    def test_bundle_creation_and_correlation(self):
        self.assertFalse(EvidenceCorrelationEngine().validate(self.bundle()))

    def test_missing_and_conflicting_data_are_reported(self):
        bundle = self.bundle()
        event = bundle.events[1]
        broken_event = type(event)(event.event_id, event.timestamp, "other", event.trace_id, event.source, event.event_type, event.phase_before, event.phase_after, event.profile, event.reason, event.severity, event.activity, event.metadata)
        codes = {item.code for item in EvidenceCorrelationEngine().validate(ShadowEvidenceBundle("e", "o", "s", "t", 3, events=(bundle.events[0], broken_event)))}
        self.assertIn("CONFLICTING_SESSION", codes)

    def test_replay_reconstructs_without_execution(self):
        result = ShadowReplayEngine().replay(self.bundle())
        self.assertEqual("mix", result.reconstructed_timeline.current_phase)
        self.assertTrue(result.decisions)
        self.assertFalse(result.execution_performed)

    def test_persistence_namespace_isolation(self):
        store = ShadowRuntimeEvidenceNamespace()
        bundle = self.bundle()
        store.store(bundle, ShadowReplayEngine().replay(bundle))
        self.assertEqual("shadow_runtime_evidence", store.namespace)
        self.assertEqual(1, len(store.bundles()))
        with self.assertRaises(RuntimeError):
            store.restore_runtime_state(bundle)

    def test_no_physical_or_transport_imports(self):
        source = (ROOT / "v3_core" / "shadow_runtime_evidence.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "paramiko", "requests", "esphome", "serial"})
        for token in ("output_on", "output_off", "set_voltage", "set_current", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
