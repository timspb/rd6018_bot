"""Deterministic contract tests for the additive AD010 diagnostic sidecar."""

from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AD008 = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad008_20261113.csv"
AD010 = ROOT / ".recipe-studio-local/mod_p1_owner_decisions_ad010_20261113.csv"
REPORT = ROOT / ".recipe-studio-local/REPORT_MOD_P1_AD010_OWNER_RECONCILIATION_20261113.md"
SCRIPT = ROOT / "tools/architecture/reconcile_owner_decisions_ad010.py"
MANUAL_STORE = "runtime/charge/manual_session_store.py"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


class AD010OwnerDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("ad010_reconcile", SCRIPT)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_preserves_old_480_rows_and_adds_exact_481st_approved_row(self) -> None:
        old_fields, old_rows = read_csv(AD008)
        fields, rows = self.module.build_rows()
        self.assertEqual(len(rows), 481)
        self.assertEqual(fields[:len(old_fields)], old_fields)
        self.assertEqual(
            [{key: row[key] for key in old_fields} for row in rows[:480]],
            old_rows,
        )
        self.assertEqual(rows[-1]["path"], MANUAL_STORE)
        self.assertEqual(len({row["path"] for row in rows}), 481)
        self.assertEqual(rows[-1]["existing_candidate"], "NO_AD004_CANDIDATE")
        self.assertEqual(rows[-1]["proposed_owner"], "REVIEW_REQUIRED")
        self.assertEqual(rows[-1]["inventory_provenance"], "untracked_at_HEAD")
        self.assertEqual(rows[-1]["AD008_approved_primary_owner"], "")
        self.assertEqual(rows[-1]["AD008_approval_status"], "")
        self.assertEqual(rows[-1]["AD008_decision_provenance"], "")
        self.assertEqual(rows[-1]["approved_primary_owner"], "")
        self.assertEqual(rows[-1]["approval_status"], "")
        self.assertEqual(rows[-1]["decision_provenance"], "")
        self.assertEqual(rows[-1]["final_owner"], "")
        self.assertIn("manual_mode.py:17", rows[-1]["source_caller_evidence"])
        self.assertIn("manual_session_store.py:19", rows[-1]["source_caller_evidence"])

    def test_exact_21_approved_and_460_pending_with_all_final_owner_blank(self) -> None:
        _, rows = self.module.build_rows()
        approved = sum(bool(row.get("approved_primary_owner")) for row in rows)
        approved += sum(bool(row.get("AD008_approved_primary_owner")) for row in rows)
        approved += sum(bool(row.get("ad010_primary_owner")) for row in rows)
        self.assertEqual(approved, 21)
        self.assertEqual(len(rows) - approved, 460)
        self.assertTrue(all(row.get("final_owner", "") == "" for row in rows))
        self.assertEqual(sum(bool(row["ad010_primary_owner"]) for row in rows), 6)

    def test_three_untracked_provenance_rows_and_off_conditions_stays_unapproved(self) -> None:
        _, rows = self.module.build_rows()
        by_path = {row["path"]: row for row in rows}
        additions = {
            "runtime/operator/off_conditions.py",
            "runtime/charge/evidence/adopted_mix_prior_age.py",
            MANUAL_STORE,
        }
        self.assertEqual({path for path, row in by_path.items() if row["inventory_provenance"] == "untracked_at_HEAD"}, additions)
        self.assertEqual(by_path["runtime/operator/off_conditions.py"]["ad010_primary_owner"], "")
        self.assertEqual(by_path["runtime/charge/evidence/adopted_mix_prior_age.py"]["ad010_primary_owner"], "Telemetry/Evidence")
        self.assertEqual(by_path[MANUAL_STORE]["ad010_primary_owner"], "Sessions & Persistence")

    def test_output_deterministic_through_in_process_generator(self) -> None:
        first = self.module.render_csv()
        second = self.module.render_csv()
        self.assertEqual(first, second)
        output_fields = next(csv.reader([first.splitlines()[0]]))
        self.assertIn("ad010_primary_owner", output_fields)
        output_rows = list(csv.DictReader(first.splitlines()))
        self.assertEqual(len(output_rows), 481)
        self.assertEqual(self.module.render_report(), self.module.render_report())

    def test_duplicate_and_missing_path_fail_closed(self) -> None:
        fields, rows = read_csv(AD008)
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.csv"
            duplicate_rows = rows + [dict(rows[0])]
            with malformed.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(duplicate_rows)
            with patch.object(self.module, "AD008_SIDECAR", malformed):
                with self.assertRaisesRegex(ValueError, "exactly 480 unique paths"):
                    self.module._read_ad008()
            missing_rows = [row for row in rows if row["path"] != "runtime/charge/battery.py"]
            with malformed.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(missing_rows)
            with patch.object(self.module, "AD008_SIDECAR", malformed):
                with self.assertRaisesRegex(ValueError, "exactly 480 unique paths"):
                    self.module._read_ad008()

    def test_bad_base_and_wrong_adr_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bad_base = Path(directory) / "bad.csv"
            bad_base.write_text("path,final_owner\nonly.py,\n", encoding="utf-8")
            with patch.object(self.module, "AD008_SIDECAR", bad_base):
                with self.assertRaisesRegex(ValueError, "exactly 480 unique paths"):
                    self.module._read_ad008()
            wrong_adr = Path(directory) / "wrong.md"
            wrong_adr.write_text("# no decisions\n", encoding="utf-8")
            with patch.object(self.module, "ADR", wrong_adr):
                with self.assertRaisesRegex(ValueError, "AD010 ADR missing exact owner mapping"):
                    self.module.build_rows()

    def test_outputs_written_from_generator_are_byte_deterministic(self) -> None:
        self.module.write_outputs()
        first_csv, first_report = AD010.read_bytes(), REPORT.read_bytes()
        self.module.write_outputs()
        self.assertEqual(AD010.read_bytes(), first_csv)
        self.assertEqual(REPORT.read_bytes(), first_report)
        fields, rows = read_csv(AD010)
        self.assertEqual(len(rows), 481)
        self.assertEqual(rows[-1]["path"], MANUAL_STORE)
        self.assertIn("ad010_primary_owner", fields)


if __name__ == "__main__":
    unittest.main()
