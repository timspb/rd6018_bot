"""Contract tests for the additive AD014 owner decision sidecar."""

from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AD012 = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_coverage_ad012_20261113.csv"
AD010 = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad010_20261113.csv"
SCRIPT = ROOT / "tools/architecture/reconcile_owner_decisions_ad014.py"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


class AD014OwnerDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("ad014_reconcile", SCRIPT)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exact_499_path_set_and_all_ad012_rows_and_fields_are_preserved(self) -> None:
        old_fields, old_rows = read_csv(AD012)
        fields, rows = self.module.build_rows()
        self.assertEqual(len(rows), 499)
        self.assertEqual(len({row["path"] for row in rows}), 499)
        self.assertEqual({row["path"] for row in rows}, {row["path"] for row in old_rows})
        self.assertEqual(fields[: len(old_fields)], old_fields)
        self.assertEqual(
            [{field: row[field] for field in old_fields} for row in rows],
            old_rows,
        )
        self.assertEqual(fields[-3:], self.module.AD014_FIELDS)
        self.assertTrue(all(row["final_owner"] == "" for row in rows))
        self.assertEqual(
            [(row["inventory_provenance"], row["working_set_status"]) for row in rows],
            [(row["inventory_provenance"], row["working_set_status"]) for row in old_rows],
        )

    def test_all_21_old_approvals_and_five_disjoint_ad014_decisions_are_exact(self) -> None:
        _, rows = self.module.build_rows()
        old_approvals = {}
        for field in ("approved_primary_owner", "AD008_approved_primary_owner", "ad010_primary_owner"):
            old_approvals.update({row["path"]: row[field] for row in rows if row[field]})
        self.assertEqual(old_approvals, {
            **self.module.AD006_APPROVALS,
            **self.module.AD008_APPROVALS,
            **self.module.AD010_APPROVALS,
        })
        ad014 = {row["path"]: row["ad014_primary_owner"] for row in rows if row["ad014_primary_owner"]}
        self.assertEqual(ad014, self.module.AD014_APPROVALS)
        self.assertFalse(set(old_approvals) & set(ad014))
        approved = len(old_approvals) + len(ad014)
        self.assertEqual(approved, 26)
        self.assertEqual(len(rows) - approved, 473)
        self.assertTrue(all(row["ad014_decision_status"] == "APPROVED_PRIMARY_OWNER_ONLY" for row in rows if row["path"] in ad014))
        self.assertTrue(all(row["ad014_provenance"] == self.module.AD014_PROVENANCE for row in rows if row["path"] in ad014))
        self.assertEqual(sum(bool(row["ad014_primary_owner"]) for row in rows), 5)

    def test_unapproved_additions_and_manual_restore_scope_stay_unassigned(self) -> None:
        _, rows = self.module.build_rows()
        by_path = {row["path"]: row for row in rows}
        _, original_rows = read_csv(AD012)
        original_by_path = {row["path"]: row for row in original_rows}
        additions = self.module.AD012_ADDITIONS
        self.assertEqual(len(additions), 18)
        self.assertEqual({path for path in additions if by_path[path]["ad014_primary_owner"]}, set(self.module.AD014_APPROVALS))
        for path in additions - set(self.module.AD014_APPROVALS):
            self.assertEqual(by_path[path]["ad014_primary_owner"], "", path)
            self.assertEqual(by_path[path]["ad014_decision_status"], "", path)
            self.assertEqual(by_path[path]["ad014_provenance"], "", path)
        for path in (
            "application/manual_start_use_case.py",
            "application/manual_stop_use_case.py",
            "application/operator_pause_use_case.py",
            "runtime/charge/restore_admission.py",
            "runtime/charge/restore_finalization.py",
            "runtime/charge/restore_projection.py",
            "runtime/operator/__init__.py",
        ):
            self.assertEqual(by_path[path]["ad014_primary_owner"], "")
        for row in rows:
            original = original_by_path[row["path"]]
            self.assertEqual(row["inventory_provenance"], original["inventory_provenance"])
            self.assertEqual(row["working_set_status"], original["working_set_status"])

    def test_deterministic_in_process_generation_uses_no_subprocess_handles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.csv"
            report = Path(directory) / "report.md"
            with patch.object(self.module, "SIDECAR", output), patch.object(self.module, "REPORT", report):
                first_csv = self.module.render_csv()
                first_report = self.module.render_report()
                self.module.write_outputs()
                first_bytes = output.read_bytes(), report.read_bytes()
                self.module.write_outputs()
                self.assertEqual(output.read_bytes(), first_bytes[0])
                self.assertEqual(report.read_bytes(), first_bytes[1])
                self.assertEqual(first_bytes, (first_csv.encode(), first_report.encode()))
                self.assertEqual(self.module.render_csv(), first_csv)
                self.assertEqual(self.module.render_report(), first_report)

    def test_missing_ad014_label_and_missing_or_duplicate_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            bad_adr = directory_path / "missing-label.md"
            bad_adr.write_text("# Missing owner decision\n", encoding="utf-8")
            with patch.object(self.module, "ADR", bad_adr):
                with self.assertRaisesRegex(ValueError, "AD014 ADR missing exact owner label"):
                    self.module.build_rows()

            fields, rows = read_csv(AD012)
            malformed = directory_path / "malformed.csv"
            target = "runtime/charge/evidence/adopted_mix_source_timestamp.py"
            missing = [row for row in rows if row["path"] != target]
            with malformed.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(missing)
            with patch.object(self.module, "AD012_SIDECAR", malformed):
                with self.assertRaisesRegex(ValueError, "499 unique paths"):
                    self.module.build_rows()

            duplicate = rows + [dict(rows[0])]
            with malformed.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(duplicate)
            with patch.object(self.module, "AD012_SIDECAR", malformed):
                with self.assertRaisesRegex(ValueError, "499 unique paths"):
                    self.module.build_rows()

    def test_prior_owner_conflict_or_changed_registry_value_fails_closed(self) -> None:
        fields, rows = read_csv(AD012)
        target = "runtime/charge/evidence/adopted_mix_source_timestamp.py"
        for row in rows:
            if row["path"] == target:
                row["ad010_primary_owner"] = "Safety"
                row["ad010_decision_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
                break
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "altered.csv"
            with altered.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with patch.object(self.module, "AD012_SIDECAR", altered):
                with self.assertRaisesRegex(ValueError, "AD010 registry values changed"):
                    self.module.build_rows()


if __name__ == "__main__":
    unittest.main()
