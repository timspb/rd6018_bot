import ast
import unittest
from pathlib import Path

from v3_core.hardware_validation import ShadowComparisonCategory, compare_shadow_observation
from v3_core.live_shadow import LiveShadowEvidenceCollector, SessionEvidence, snapshot_hash


ROOT = Path(__file__).resolve().parents[1]


class Workstream12LiveShadowTests(unittest.TestCase):
    def test_record_hash_trace_and_session_correlation(self):
        collector = LiveShadowEvidenceCollector()
        collector.register_session(SessionEvidence("s1", 1.0, "AGM"))
        comparison = compare_shadow_observation({"phase": "CV"}, {"phase": "CV"})
        record = collector.record(timestamp=2.0, trace_id="t1", session_id="s1", source="V2", input_snapshot={"v": 14.8}, comparison=comparison)
        self.assertEqual(snapshot_hash({"v": 14.8}), record.input_snapshot_hash)
        self.assertEqual("s1", collector.sessions()[0].session_id)
        self.assertEqual("t1", collector.evidence()[0].trace_id)

    def test_dashboard_classifies_divergence_without_deciding_or_executing(self):
        collector = LiveShadowEvidenceCollector()
        comparison = compare_shadow_observation({"phase": "CC"}, {"phase": "CV"})
        collector.record(timestamp=1.0, trace_id="t", session_id="s", source="V2", input_snapshot={}, comparison=comparison)
        self.assertEqual(ShadowComparisonCategory.WARNING, comparison.category)
        self.assertEqual("WARNING", collector.dashboard().parity_status)
        self.assertEqual("OBSERVING", collector.dashboard().health)

    def test_no_external_or_write_symbols(self):
        source = (ROOT / "v3_core" / "live_shadow.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"set_voltage", "set_current", "output_on", "output_off", "turn_on", "turn_off", "write", "requests", "aiohttp"}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(forbidden & (names | attrs))


if __name__ == "__main__":
    unittest.main()
