"""Deterministic contract tests for the additive AD008 diagnostic sidecar."""

from __future__ import annotations

import csv
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AD006 = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad006_20261113.csv"
AD008 = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad008_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD008_OWNER_RECONCILIATION_20261113.md"
SCRIPT = ROOT / "tools/architecture/reconcile_owner_decisions_ad008.py"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


class AD008OwnerDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("ad008_reconcile", SCRIPT)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exact_ten_ad008_mappings_and_fifteen_total_approvals(self) -> None:
        _, rows = self.module.build_rows()
        ad008 = {r["path"]: r["AD008_approved_primary_owner"] for r in rows if r["AD008_approval_status"]}
        self.assertEqual(ad008, self.module.AD008_APPROVALS)
        prior = {r["path"]: r["approved_primary_owner"] for r in rows if r["approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY"}
        self.assertEqual(prior, self.module.AD006_APPROVALS)
        self.assertEqual(len(ad008) + len(prior), 15)
        self.assertEqual(sum(not r["AD008_approval_status"] and r["approval_status"] != "APPROVED_PRIMARY_OWNER_ONLY" for r in rows), 465)

    def test_preserves_ad006_rows_and_all_original_fields_and_keeps_final_owner_empty(self) -> None:
        old_fields, old_rows = read_csv(AD006)
        new_fields, rows = self.module.build_rows()
        old_by_path = {r["path"]: r for r in old_rows}
        new_by_path = {r["path"]: r for r in rows}
        self.assertEqual(len(rows), 480)
        self.assertEqual(len(new_by_path), 480)
        self.assertEqual(set(new_by_path), set(old_by_path))
        self.assertEqual(new_fields, old_fields + self.module.AD008_FIELDS)
        for path, old in old_by_path.items():
            for field in old_fields:
                self.assertEqual(new_by_path[path][field], old[field], (path, field))
        self.assertTrue(all(not r["final_owner"] for r in rows))
        for path in ("runtime/operator/off_conditions.py", "runtime/charge/evidence/adopted_mix_prior_age.py"):
            row = new_by_path[path]
            self.assertEqual(row["approval_status"], "UNAPPROVED")
            self.assertEqual(row["AD008_approved_primary_owner"], "")

    def test_generated_outputs_are_deterministic_without_subprocess(self) -> None:
        self.module.write_outputs()
        first = (AD008.read_bytes(), REPORT.read_bytes())
        self.module.write_outputs()
        self.assertEqual(first, (AD008.read_bytes(), REPORT.read_bytes()))
        report = first[1].decode("utf-8")
        self.assertIn("total approved: 15; pending: 465", report)
        self.assertIn("Every `final_owner` remains empty", report)
        self.assertIn("do not claim exclusive command authority", report)

    def test_source_inventory_is_never_written_by_generator(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("AD006_SIDECAR", source)
        self.assertNotIn("AD006_SIDECAR.write_text", source)
        self.assertIn("refusing ambiguous reconciliation", source)
        self.assertIn("AD008 ADR missing exact owner mapping", source)


if __name__ == "__main__":
    unittest.main()
