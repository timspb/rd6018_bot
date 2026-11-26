"""Read-only deterministic contract for the P1-AD004 owner evidence artifact."""
from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/architecture/build_owner_evidence_ad004.py"
PREPARER_SCRIPT = ROOT / "tools/architecture/prepare_historical_test_inputs.py"
PREPARER_SPEC = importlib.util.spec_from_file_location("prepare_historical_test_inputs", PREPARER_SCRIPT)
PREPARER = importlib.util.module_from_spec(PREPARER_SPEC)
assert PREPARER_SPEC and PREPARER_SPEC.loader
PREPARER_SPEC.loader.exec_module(PREPARER)
SPEC = importlib.util.spec_from_file_location("owner_evidence_ad004", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class OwnerEvidenceAD004Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._preimage_temp = tempfile.TemporaryDirectory(prefix="rd6018-ad004-test-preimage-")
        cls.source_root = PREPARER.materialize_source_preimage(
            Path(cls._preimage_temp.name) / "source", root=ROOT
        )

    @classmethod
    def tearDownClass(cls):
        cls._preimage_temp.cleanup()

    def test_sidecar_matches_exact_478_path_set_and_inventory_stays_unassigned(self):
        source_before = MODULE.INVENTORY.read_bytes()
        rows, _ = MODULE.build_rows(self.source_root)
        _, source = MODULE.read_inventory()
        self.assertEqual(source_before, MODULE.INVENTORY.read_bytes())
        self.assertEqual(478, len(rows))
        self.assertEqual(478, len({row["path"] for row in rows}))
        self.assertEqual({row["path"] for row in source}, {row["path"] for row in rows})
        self.assertTrue(all((self.source_root / row["path"]).is_file() for row in rows))
        self.assertTrue(all(not row["final_owner"] for row in source))
        self.assertNotIn("final_owner", MODULE.FIELDS)

    def test_review_flags_side_effect_evidence_and_uncertainty_are_retained(self):
        rows, _ = MODULE.build_rows(self.source_root)
        by_path = {row["path"]: row for row in rows}
        _, source = MODULE.read_inventory()
        review = [row for row in source if row["proposed_owner_candidate"] == "REVIEW_REQUIRED"]
        self.assertEqual(82, len(review))
        for row in review:
            sidecar = by_path[row["path"]]
            if row["review_flags"]:
                self.assertIn(row["review_flags"], sidecar["review_reason"])
            if row["proposed_owner_candidate"] == "REVIEW_REQUIRED":
                self.assertIn(sidecar["confidence"], {"medium", "uncertain"})
                self.assertIn("candidate intentionally unresolved", sidecar["review_reason"])
        for row in source:
            if row["observed_side_effect_indicators"]:
                sidecar = by_path[row["path"]]
                self.assertEqual(row["observed_side_effect_indicators"], sidecar["side_effect_type"])
                self.assertIn("side-effect indicator", sidecar["review_reason"])

    def test_owner_taxonomy_and_mixed_responsibilities_remain_unresolved(self):
        rows, _ = MODULE.build_rows(self.source_root)
        self.assertTrue(set(MODULE.OWNERS.values()).issubset({r["proposed_owner"] for r in rows}))
        for row in rows:
            self.assertIn(row["proposed_owner"], MODULE.OWNER_TAXONOMY)
            self.assertIn(row["confidence"], {"high", "medium", "uncertain"})
            self.assertTrue(row["evidence"])
            self.assertTrue(row["review_reason"])
            if row["confidence"] == "uncertain":
                self.assertTrue(any(word in row["review_reason"] for word in ("unresolved", "mixed", "parse", "unproven", "side-effect")))
            if row["mixed_responsibility"] == "true":
                self.assertEqual("REVIEW_REQUIRED", row["proposed_owner"])
                self.assertEqual("uncertain", row["confidence"])

    def test_report_contains_all_review_dispositions_and_top_fifteen_mixed(self):
        rows, _ = MODULE.build_rows(self.source_root)
        _, inventory = MODULE.read_inventory()
        report = MODULE.render_report(rows, [], inventory)
        self.assertIn("Prioritized 15 mixed modules", report)
        self.assertEqual(82, sum(1 for row in inventory if row["proposed_owner_candidate"] == "REVIEW_REQUIRED"))
        self.assertEqual(82, sum(1 for line in report.splitlines() if line.startswith("| `") and " | " in line))
        self.assertIn("High confidence:", report)
        self.assertIn("uncertain:", report)

    def test_csv_utf8_bom_parseability_and_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "a.csv", Path(temp) / "b.csv"
            rows, _ = MODULE.build_rows(self.source_root)
            MODULE.write_csv(first, rows)
            MODULE.write_csv(second, rows)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertTrue(first.read_bytes().startswith(b"\xef\xbb\xbf"))
            with first.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(MODULE.FIELDS, reader.fieldnames)
                self.assertEqual(478, len(list(reader)))


if __name__ == "__main__":
    unittest.main()
