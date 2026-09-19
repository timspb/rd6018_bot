import ast
import unittest
from pathlib import Path

from application.live_charge_cycle import LiveChargeCycleObserver, SourceCorrelation
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


ROOT = Path(__file__).resolve().parents[1]


def full_events():
    kinds = (EventType.SESSION_STARTED, EventType.PHASE_STARTED, EventType.PHASE_TRANSITION, EventType.DELTA_STARTED, EventType.DELTA_COMPLETED, EventType.HOLD_STARTED, EventType.HOLD_COMPLETED, EventType.TERMINATION_DETECTED, EventType.SESSION_STOPPED)
    return tuple(CanonicalChargeEvent(str(i), float(i), "s", "t", EventSource.JOURNAL, kind, phase_before="main" if kind is EventType.PHASE_TRANSITION else None, phase_after="mix" if kind is EventType.PHASE_TRANSITION else None, metadata={"telemetry_ref": f"tel-{i}"}) for i, kind in enumerate(kinds, 1))


class Workstream22LiveChargeCycleTests(unittest.TestCase):
    def test_detects_current_session_from_supplied_sources(self):
        state = LiveChargeCycleObserver().detect(session={"session_id": "s", "battery": "Baic72", "stage": "mix", "started_at": 1}, rd={}, esphome={}, ha={})
        self.assertEqual(("s", "Baic72", "mix"), (state.session_id, state.profile, state.phase))

    def test_full_lifecycle_capture_replays_without_execution(self):
        evidence = LiveChargeCycleObserver().capture(events=full_events(), session_id="s", evidence_id="e", observation_id="o", created_at=20)
        self.assertTrue(evidence.chain_result.complete)
        self.assertIsNotNone(evidence.replay_result)
        self.assertFalse(evidence.replay_result.execution_performed)
        self.assertEqual(9, len(evidence.timeline))

    def test_source_correlation_and_conflict(self):
        result = LiveChargeCycleObserver().correlate({"ESP": {"voltage": 17.14}, "HA": {"voltage": 17.15}, "RD": {"voltage": 17.14, "mode": "CC"}})
        by_field = {item.field: item.classification for item in result}
        self.assertEqual(SourceCorrelation.MATCH, by_field["voltage"])
        self.assertEqual(SourceCorrelation.EXPECTED_DIFFERENCE, by_field["mode"])

    def test_no_write_or_execution_imports(self):
        source = (ROOT / "application" / "live_charge_cycle.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "requests", "serial"})
        for token in ("output_on", "output_off", "set_voltage", "set_current", "controller.start", "controller.stop", "lease_renew"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
