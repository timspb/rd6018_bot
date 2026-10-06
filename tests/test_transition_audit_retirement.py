from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TransitionAuditRetirementTests(unittest.TestCase):
    def test_legacy_transition_decision_source_is_removed(self):
        self.assertFalse((ROOT / "legacy_transition_audit.py").exists())

    def test_production_graph_has_no_legacy_transition_audit_reference(self):
        violations = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith("tests/"):
                continue
            source = path.read_text(encoding="utf-8")
            if "legacy_transition_audit" in source:
                violations.append(rel)
        self.assertEqual([], violations)

    def test_historical_trace_columns_remain_readable(self):
        store = (ROOT / "recovery_trace_store.py").read_text(encoding="utf-8")
        report = (ROOT / "recovery_trace_report.py").read_text(encoding="utf-8")
        self.assertIn("transition_audit_code", store)
        self.assertIn("transition_audit_severity", store)
        self.assertIn('"transition_audits"', report)


if __name__ == "__main__":
    unittest.main()
