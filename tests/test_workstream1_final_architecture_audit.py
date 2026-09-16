"""WORKSTREAM 1 final architecture audit checks; read-only only."""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
AUDIT = DOCS / "RD6018_V3_FINAL_ARCHITECTURE_AUDIT.md"
CANONICAL = DOCS / "RD6018_V3_CANONICAL_STATE.md"
GUARDRAILS = DOCS / "RD6018_ARCHITECTURE_GUARDRAILS.md"


class Workstream1FinalArchitectureAuditTests(unittest.TestCase):
    def test_source_documents_and_audit_sections_exist(self):
        self.assertTrue(AUDIT.exists())
        self.assertTrue(CANONICAL.exists())
        self.assertTrue(GUARDRAILS.exists())
        self.assertGreater(len(list(DOCS.glob("RD6018_*_MODEL.md"))), 20)
        text = AUDIT.read_text(encoding="utf-8")
        for section in (
            "Module isolation audit", "Ownership audit", "Hidden coupling audit",
            "Configuration audit", "Safety audit", "Runtime audit",
            "Migration readiness by stage", "Technical debt register",
        ):
            self.assertIn(section, text)

    def test_ownership_matrix_is_complete_and_v2_execution_remains_owner(self):
        text = AUDIT.read_text(encoding="utf-8")
        for authority in (
            "Telemetry", "Configuration", "Diagnostics", "Persistence", "Domain",
            "Decision", "Safety/containment", "Execution", "Lease", "Physical output",
        ):
            self.assertIn(f"| {authority} |", text)
        self.assertIn("V2 remains execution owner", text)
        self.assertIn("V2 remains physical", text)
        self.assertIn("owner** until", text)
        self.assertIn("approved dual *active* owner", text)

    def test_pure_v3_contract_modules_remain_isolated(self):
        modules = (
            "decision_authority.py", "decision_authority_shadow_run.py", "decision_canary.py",
            "decision_cutover_readiness.py", "decision_cutover_operational_readiness.py",
            "diagnostics_domain.py", "persistence_boundary.py", "staged_ownership.py",
            "v2_v3_comparison.py",
        )
        forbidden = ("hass", "homeassistant", "esphome", "transport", "controller", "lease", "physical", "output")
        for name in modules:
            path = ROOT / "application" / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name.lower() for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append((node.module or "").lower())
            self.assertEqual([], [item for item in imports if any(term in item for term in forbidden)], name)

    def test_configuration_completeness_and_known_conflicts_are_explicit(self):
        text = AUDIT.read_text(encoding="utf-8")
        for section in ("charge", "strategy", "safety", "containment", "lease", "execution", "transport", "UI", "persistence"):
            self.assertIn(section, text.lower() if section != "UI" else text)
        for conflict in (
            "EFB Mix budget 20 h versus 24 h", "watchdog 180 s versus 300 s",
            "readback/settle windows", "transport default/priority disagreement",
        ):
            self.assertIn(conflict, text)
        self.assertIn("CONFIGURATION_MIGRATION_INVENTORY", text)

    def test_invariants_and_stage_blockers_are_explicit(self):
        text = AUDIT.read_text(encoding="utf-8")
        for marker in (
            "Status: NOT READY FOR REAL OWNERSHIP TRANSITIONS",
            "Stage 0", "Stage 1", "Stage 2", "Stage 3",
            "ACT-B01", "CFG-B01", "SAFE-B01",
            "No runtime lifecycle was changed",
            "This audit did not change V2 runtime",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
