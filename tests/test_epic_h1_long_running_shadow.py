"""EPIC H.1 long-running shadow acceptance tests."""

import ast
from pathlib import Path
import unittest

from application.long_running_shadow_acceptance import AcceptanceBand, ShadowAcceptanceCollector
from application.v2_v3_comparison import ComparisonStatus


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "application" / "long_running_shadow_acceptance.py"
DOC = ROOT / "docs" / "RD6018_LONG_RUNNING_SHADOW_ACCEPTANCE_MODEL.md"
CANONICAL = ROOT / "docs" / "RD6018_V3_CANONICAL_STATE.md"


class EpicH1LongRunningShadowTests(unittest.TestCase):
    def test_metric_aggregation(self):
        collector = ShadowAcceptanceCollector()
        collector.record_decision(ComparisonStatus.EQUAL)
        collector.record_decision(ComparisonStatus.EXPECTED_DIFFERENCE)
        collector.record_decision(ComparisonStatus.CONFLICT)
        collector.record_decision(ComparisonStatus.UNKNOWN)
        collector.record_execution(intent_equal=True, safety_gate_equal=True, verification_equal=True)
        collector.record_runtime(v2_healthy=True, v3_healthy=True)
        collector.record_safety(stale_telemetry=2)
        result = collector.evaluate()
        self.assertEqual(1, result.decision.equal)
        self.assertEqual(4, result.decision.total)
        self.assertEqual(2, result.safety.stale_telemetry_events)
        self.assertFalse(result.ownership_changed)

    def test_warning_and_pass_threshold_evaluation(self):
        collector = ShadowAcceptanceCollector()
        for _ in range(100):
            collector.record_decision(ComparisonStatus.EQUAL)
        collector.record_execution(intent_equal=True, safety_gate_equal=True, verification_equal=True)
        collector.record_runtime(v2_healthy=True, v3_healthy=True)
        result = collector.evaluate()
        self.assertEqual(AcceptanceBand.PASS, result.decision_band)
        self.assertEqual(AcceptanceBand.PASS, result.execution_band)

        warning = ShadowAcceptanceCollector()
        warning.record_decision(ComparisonStatus.EQUAL)
        self.assertEqual(AcceptanceBand.WARNING, warning.evaluate().decision_band)

    def test_blocker_detection(self):
        collector = ShadowAcceptanceCollector()
        for _ in range(10):
            collector.record_decision(ComparisonStatus.CONFLICT)
        collector.record_execution(intent_equal=False, safety_gate_equal=True, verification_equal=False)
        collector.record_runtime(v2_healthy=True, v3_healthy=False, restart=True, worker_failure=True)
        collector.record_safety(containment_divergence=1, lease_divergence=1)
        collector.record_configuration(unresolved_usage=1, provenance_conflict=1)
        result = collector.evaluate()
        self.assertEqual(AcceptanceBand.BLOCKED, result.decision_band)
        for blocker in ("decision_conflict_rate", "execution_parity", "runtime_health", "safety_divergence", "configuration_conflict"):
            self.assertIn(blocker, result.blockers)
        self.assertFalse(result.ownership_changed)

    def test_no_physical_or_ownership_side_effects(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append((node.module or "").lower())
        forbidden = ("execution", "controller", "hass", "homeassistant", "esphome", "lease", "physical", "output")
        self.assertEqual([], [name for name in imports if any(token in name for token in forbidden)])
        source = MODULE.read_text(encoding="utf-8")
        for token in ("dispatch(", "output_on(", "output_off(", "set_voltage(", "set_current(", "renew", "owner ="):
            self.assertNotIn(token, source)

    def test_document_and_canonical_status(self):
        text = DOC.read_text(encoding="utf-8")
        for term in ("Decision metrics", "Execution metrics", "Runtime metrics", "Safety metrics", "Configuration metrics", "PASS", "WARNING", "BLOCKED"):
            self.assertIn(term, text)
        canonical = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("### EPIC H.1 — Long-running shadow acceptance", canonical)
        self.assertIn("Current status: long-running shadow observation", canonical)


if __name__ == "__main__":
    unittest.main()
