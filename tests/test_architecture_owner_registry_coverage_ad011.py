from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools/architecture/audit_owner_registry_coverage_ad011.py"
spec = importlib.util.spec_from_file_location("coverage_ad011", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class CoverageAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry.csv"
        fields = ["path", "approved_primary_owner", "AD008_approved_primary_owner", "ad010_primary_owner", "final_owner"]
        with self.registry.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for i in range(481):
                writer.writerow({"path": f"runtime/base_{i:03}.py", "approved_primary_owner": "Owner" if i < 5 else "",
                                 "AD008_approved_primary_owner": "Owner" if 5 <= i < 15 else "",
                                 "ad010_primary_owner": "Owner" if 15 <= i < 21 else "", "final_owner": ""})
        for p in ("runtime/base_000.py", "runtime/base_001.py", "runtime/new_prod.py", "tests/test_only.py",
                  "tools/helper.py", ".worktrees/shadow/pkg.py", ".venv/lib/site-packages/x.py",
                  ".recipe-studio-local/local.py", ".hidden/helper.py", "runtime/cache/__pycache__/z.py"):
            target = self.root / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("from runtime.new_prod import f\n" if p == "runtime/base_000.py" else "def f(): pass\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_audit(self, tracked, untracked, ignored=()):
        return module.audit(self.root, self.registry, tracked_paths=set(tracked),
                            untracked_paths=set(untracked), ignored_paths=set(ignored))

    def test_classifies_gaps_missing_paths_and_exclusions(self):
        tracked = {"runtime/base_000.py", "runtime/base_001.py", "tests/test_only.py", "tools/helper.py"}
        untracked = {"runtime/new_prod.py", ".worktrees/shadow/pkg.py", ".venv/lib/site-packages/x.py",
                     ".recipe-studio-local/local.py", ".hidden/helper.py", "runtime/cache/__pycache__/z.py"}
        rows, counts = self.run_audit(tracked, untracked, {"runtime/new_prod.py"})
        by = {r["path"]: r for r in rows}
        self.assertEqual(481, counts["registry_paths"])
        self.assertEqual(21, counts["registry_approved"])
        self.assertEqual("missing", by["runtime/base_002.py"]["git_status"])
        self.assertEqual("uncertain", by["runtime/base_002.py"]["proposed_is_production"])
        self.assertEqual("uncertain", by["runtime/new_prod.py"]["proposed_is_production"])
        self.assertEqual("yes", by["runtime/new_prod.py"]["ignored"])
        for path in ("tests/test_only.py", "tools/helper.py", ".worktrees/shadow/pkg.py", ".venv/lib/site-packages/x.py",
                     ".recipe-studio-local/local.py", ".hidden/helper.py", "runtime/cache/__pycache__/z.py"):
            self.assertEqual("no", by[path]["proposed_is_production"], path)
        self.assertTrue(by["runtime/new_prod.py"]["source_import_consumers"])
        self.assertTrue(all(r["owner_approval"] == "NEVER_ASSIGNED" for r in rows))

    def test_deterministic_csv_and_no_registry_or_source_writes(self):
        tracked = {"runtime/base_000.py", "runtime/base_001.py"}
        untracked = {"runtime/new_prod.py"}
        before_registry = self.registry.read_bytes()
        before_source = (self.root / "runtime/base_000.py").read_bytes()
        rows1, _ = self.run_audit(tracked, untracked)
        rows2, _ = self.run_audit(tracked, untracked)
        with tempfile.TemporaryDirectory() as out:
            first, second = Path(out) / "a.csv", Path(out) / "b.csv"
            module.write_csv(first, rows1)
            module.write_csv(second, rows2)
            self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(before_registry, self.registry.read_bytes())
        self.assertEqual(before_source, (self.root / "runtime/base_000.py").read_bytes())

    def test_rejects_registry_count_or_approval_drift(self):
        rows, _ = self.run_audit({"runtime/base_000.py"}, set())
        with self.registry.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        rows[0]["approved_primary_owner"] = ""
        with self.registry.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaises(ValueError):
            module.audit(self.root, self.registry, tracked_paths={"runtime/base_000.py"}, untracked_paths=set())


if __name__ == "__main__":
    unittest.main()
