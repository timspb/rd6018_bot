import ast
import unittest
from pathlib import Path

from application.direct_evidence_sources import (
    ESPHomeEvidenceSource,
    EvidenceChainReassembler,
    TraceCorrelationValidator,
    default_runtime_event_inventory,
)
from v3_core.canonical_events import CanonicalChargeEvent, EventSource, EventType


ROOT = Path(__file__).resolve().parents[1]


class Workstream21DirectEvidenceSourceTests(unittest.TestCase):
    def test_esphome_source_accepts_state_only(self):
        source = ESPHomeEvidenceSource(lambda: {"entities": {"output": "on"}, "availability": "online", "timestamp": 10, "device_health": {"uptime": 5}})
        snapshot = source.collect()
        self.assertEqual("online", snapshot.availability)
        self.assertEqual("on", snapshot.entities["output"])

    def test_esphome_source_rejects_write_surface(self):
        with self.assertRaises(ValueError):
            ESPHomeEvidenceSource(lambda: {"entities": {}, "services": ("turn_off",)}).collect()

    def test_trace_validator_detects_orphans_and_cross_session(self):
        events = (CanonicalChargeEvent("1", 1, "s2", "t2", EventSource.JOURNAL, EventType.SESSION_STARTED),)
        codes = {issue.code for issue in TraceCorrelationValidator().validate(events, session_id="s1", trace_id="t1")}
        self.assertEqual({"ORPHAN_TRACE", "CROSS_SESSION"}, codes)

    def test_inventory_and_reassembly_are_source_only(self):
        inventory = default_runtime_event_inventory()
        self.assertEqual(6, len(inventory))
        bundle = EvidenceChainReassembler().reassemble(({"event": "START", "timestamp": 1, "metadata": {"telemetry_ref": "x"}},), session_id="s", trace_id="t", evidence_id="e", observation_id="o", created_at=2)
        self.assertEqual("s", bundle.session_id)
        self.assertEqual(EventType.SESSION_STARTED, bundle.events[0].event_type)

    def test_no_external_or_write_imports(self):
        source = (ROOT / "application" / "direct_evidence_sources.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names}
        self.assertFalse(imports & {"aiohttp", "paramiko", "requests", "esphome", "serial"})
        for token in ("turn_off", "switch_command", "output_on", "output_off", "lease_renew"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
