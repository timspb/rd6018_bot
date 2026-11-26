from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools/architecture/normalize_ownership_inventory.py"
SPEC = importlib.util.spec_from_file_location("normalize_ownership_inventory", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OwnershipInventoryNormalizationTests(unittest.TestCase):
    def row(self, path="pkg/target.py", imports_in="", imports_out="", final_owner=""):
        return {
            "path": path,
            "imports_in_count": str(len(imports_in.split(" | "))) if imports_in else "0",
            "imports_in": imports_in,
            "imports_out_count": str(len(imports_out.split(" | "))) if imports_out else "0",
            "imports_out": imports_out,
            "final_owner": final_owner,
        }

    def test_exact_duplicate_reference_removed_and_distinct_occurrences_retained(self):
        source = "pkg/source.py:10[eager]"
        rows = [
            self.row("pkg/target.py", imports_in=f"{source} | {source} | pkg/source.py:11[eager] | pkg/source.py:10[deferred]"),
            self.row("pkg/source.py", imports_out=f"pkg/target.py:3[eager] | pkg/target.py:3[eager] | pkg/target.py:4[eager] | pkg/target.py:3[deferred]"),
        ]
        result, stats = MODULE.normalize_rows(rows)
        target = next(row for row in result if row["path"] == "pkg/target.py")
        source_row = next(row for row in result if row["path"] == "pkg/source.py")
        self.assertEqual(target["imports_in_count"], "3")
        self.assertEqual(target["imports_in_distinct_occurrence_count"], "3")
        self.assertEqual(source_row["imports_out_count"], "3")
        self.assertEqual(source_row["imports_out_distinct_occurrence_count"], "3")
        self.assertEqual(stats["exact_duplicates_removed_in"], 1)
        self.assertEqual(stats["exact_duplicates_removed_out"], 1)
        self.assertEqual(stats["distinct_module_edges_in"], 2)
        self.assertEqual(stats["distinct_module_edges_out"], 2)

    def test_empty_lists_and_final_owner_are_preserved(self):
        rows, stats = MODULE.normalize_rows([self.row(final_owner="")])
        self.assertEqual(rows[0]["imports_in"], "")
        self.assertEqual(rows[0]["imports_out"], "")
        self.assertEqual(rows[0]["final_owner"], "")
        self.assertEqual(rows[0]["imports_in_count"], "0")
        self.assertEqual(stats["distinct_occurrences_in"], 0)

    def test_csv_escaping_unicode_paths_and_deterministic_order(self):
        rows = [
            self.row("zeta/路径, module.py", imports_in="alpha/é.py:1[eager]"),
            self.row("alpha/é.py", imports_out="zeta/路径, module.py:1[eager]"),
        ]
        normalized, _ = MODULE.normalize_rows(rows)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "normalized.csv"
            MODULE.write_csv(path, list(rows[0]), normalized)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                loaded = list(csv.DictReader(stream))
        self.assertEqual([row["path"] for row in loaded], ["alpha/é.py", "zeta/路径, module.py"])
        self.assertEqual(loaded[1]["path"], "zeta/路径, module.py")
        self.assertEqual(loaded[0]["imports_out"], "zeta/路径, module.py:1[eager]")

    def test_unsafe_or_malformed_import_reference_rejected(self):
        for bad in ("pkg/a.py:0[eager]", "pkg/a.py:2[unknown]", "pkg/a.py:2[eager"):
            with self.subTest(reference=bad), self.assertRaises(ValueError):
                MODULE._identity(bad)


if __name__ == "__main__":
    unittest.main()
