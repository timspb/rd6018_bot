"""Contract tests for the additive architect-approved AD-006 owner record."""

from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/architecture/reconcile_owner_decisions_ad006.py"
BASELINE = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_evidence_ad004_20261113.csv"
SIDECAR = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad006_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD006_OWNER_RECONCILIATION_20261113.md"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


class AD006OwnerDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("ad006_reconcile", SCRIPT)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exactly_five_only_architect_approvals(self) -> None:
        _, rows = self.module.build_rows()
        approved = {row["path"]: row["approved_primary_owner"] for row in rows if row["approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY"}
        self.assertEqual(approved, {
            "database.py": "Sessions & Persistence",
            "bot.py": "Composition/Configuration",
            "operator_dashboard.py": "UI",
            "ha_history.py": "Telemetry/Evidence",
            "runtime/physical/connectors/esp_direct.py": "Physical Execution",
        })
        self.assertEqual(len(approved), 5)

    def test_preserves_baseline_rows_and_adds_only_two_unapproved_gaps(self) -> None:
        base_fields, base = read_csv(BASELINE)
        _, result = self.module.build_rows()
        base_by_path = {row["path"]: row for row in base}
        result_by_path = {row["path"]: row for row in result}
        self.assertEqual(len(result), 480)
        self.assertEqual(len(result_by_path), 480)
        self.assertTrue(all(not row["final_owner"] for row in result))
        self.assertEqual(set(base_by_path), set(result_by_path) - {
            "runtime/operator/off_conditions.py",
            "runtime/charge/evidence/adopted_mix_prior_age.py",
        })
        self.assertEqual(set(result_by_path) - set(base_by_path), {
            "runtime/operator/off_conditions.py",
            "runtime/charge/evidence/adopted_mix_prior_age.py",
        })
        for path, original in base_by_path.items():
            for field in base_fields:
                self.assertEqual(result_by_path[path][field], original[field], (path, field))
        for path in set(result_by_path) - set(base_by_path):
            added = result_by_path[path]
            self.assertEqual(added["existing_candidate"], "NO_AD004_CANDIDATE")
            self.assertEqual(added["inventory_provenance"], "untracked_at_HEAD")
            self.assertEqual(added["approval_status"], "UNAPPROVED")
            self.assertIn(path, added["source_caller_evidence"])

    def test_false_charge_engine_proposals_are_not_approved_and_physical_scope_is_limited(self) -> None:
        _, rows = self.module.build_rows()
        by_path = {row["path"]: row for row in rows}
        self.assertEqual(by_path["database.py"]["proposed_owner"], "ChargeEngine")
        self.assertEqual(by_path["database.py"]["approved_primary_owner"], "Sessions & Persistence")
        self.assertEqual(by_path["runtime/__init__.py"]["proposed_owner"], "ChargeEngine")
        self.assertEqual(by_path["runtime/__init__.py"]["approved_primary_owner"], "")
        connector = by_path["runtime/physical/connectors/esp_direct.py"]
        self.assertIn("adapter module only", connector["authority_limit"].lower())
        self.assertIn("no exclusive physical command authority", connector["authority_limit"].lower())
        self.assertEqual(len([r for r in rows if r["approved_primary_owner"]]), 5)

    def test_static_source_has_no_production_imports_or_physical_authority_claim(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("import bot", source)
        self.assertNotIn("import runtime.production_runtime", source)
        self.assertIn("No owner approval", source)
        self.assertIn("not establish runtime reachability or command authority", source)

    def test_generated_files_are_deterministic_and_report_scope(self) -> None:
        self.module.write_outputs()
        first_csv, first_report = SIDECAR.read_bytes(), REPORT.read_bytes()
        self.module.write_outputs()
        self.assertEqual(first_csv, SIDECAR.read_bytes())
        self.assertEqual(first_report, REPORT.read_bytes())
        report = first_report.decode("utf-8")
        self.assertIn("exactly 5", report)
        self.assertIn("not grant exclusive physical command authority", report)
        self.assertIn("for `database.py` is rejected", report)


if __name__ == "__main__":
    unittest.main()
