"""Offline regressions for the AD012 diagnostic coverage sidecar."""
from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/architecture/reconcile_owner_coverage_ad012.py"
spec = importlib.util.spec_from_file_location("ad012_reconcile", MODULE_PATH)
ad012 = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(ad012)

EXPECTED = {
    "application/manual_cooling_use_case.py",
    "application/manual_mix_transition_use_case.py",
    "application/manual_observer_use_case.py",
    "application/manual_phase_evidence.py",
    "application/manual_start_use_case.py",
    "application/manual_stop_use_case.py",
    "application/manual_supervisor_use_case.py",
    "application/operator_pause_use_case.py",
    "runtime/charge/evidence/adopted_mix_finish_hold_decision.py",
    "runtime/charge/evidence/adopted_mix_sample_decision.py",
    "runtime/charge/evidence/adopted_mix_source_timestamp.py",
    "runtime/charge/evidence/manual_delta.py",
    "runtime/charge/restore_admission.py",
    "runtime/charge/restore_finalization.py",
    "runtime/charge/restore_projection.py",
    "runtime/charge/strategy/adopted_mix_admission.py",
    "runtime/operator/pause_state.py",
    "runtime/operator/__init__.py",
}


class OwnerCoverageAD012Tests(unittest.TestCase):
    def test_exact_scope_counts_and_field_level_baseline_preservation(self):
        fields, output = ad012.build_rows()
        original_fields, original = ad012._read_csv(ROOT / ad012.BASELINE)
        additions = output[len(original):]
        self.assertEqual(set(r["path"] for r in additions), EXPECTED)
        self.assertEqual(len(output), 499)
        self.assertEqual(len({r["path"] for r in output}), 499)
        self.assertEqual(fields, original_fields)
        self.assertEqual(output[:len(original)], original)
        self.assertTrue(all(not r["final_owner"] for r in original + additions))
        self.assertTrue(all(r["approval_status"] == "UNAPPROVED" for r in additions))
        self.assertEqual(sum(r["approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY" or r["AD008_approval_status"] == "APPROVED_PRIMARY_OWNER_ONLY" or r["ad010_decision_status"] == "APPROVED_PRIMARY_OWNER_ONLY" for r in output), 21)
        self.assertEqual(499 - 21, 478)
        audit_rows = ad012._read_csv(ROOT / ad012.AD011)[1]
        self.assertEqual(len(audit_rows), 1584)
        uncovered = [r for r in audit_rows if r["registry_membership"] == "undiscovered" and r["proposed_is_production"] == "uncertain" and r["risk"] in {"high", "medium"}]
        self.assertEqual(len(uncovered), 18)
        self.assertEqual(sum(bool(r["source_import_consumers"]) for r in uncovered), 17)
        self.assertEqual(sum(not r["source_import_consumers"] for r in uncovered), 1)
        pkg = next(r for r in additions if r["path"] == "runtime/operator/__init__.py")
        self.assertIn("no inbound", pkg["source_caller_evidence"])

    def test_missing_path_fails_closed_before_using_historical_fixture_row(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ad012.BASELINE).parent.mkdir(parents=True)
            (root / ad012.BASELINE).write_bytes((ROOT / ad012.BASELINE).read_bytes())
            (root / ad012.AD011).write_bytes((ROOT / ad012.AD011).read_bytes())
            with self.assertRaisesRegex(ValueError, "source path missing"):
                ad012.build_rows(root)

    def test_generation_is_idempotent_and_no_runtime_or_device_imports(self):
        first_paths = ad012.generate()
        first = tuple(path.read_bytes() for path in first_paths)
        second_paths = ad012.generate()
        second = tuple(path.read_bytes() for path in second_paths)
        self.assertEqual(first_paths, second_paths)
        self.assertEqual(first, second)
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import runtime", source)
        self.assertNotIn("aioesphomeapi", source)
        self.assertNotIn("hass_api", source)
        self.assertNotIn("socket", source)
        self.assertNotIn("esp_direct", source)

    def test_changed_approval_baseline_fails_closed(self):
        _, rows = ad012._read_csv(ROOT / ad012.BASELINE)
        rows[0]["ad010_decision_status"] = "APPROVED_PRIMARY_OWNER_ONLY"
        with self.assertRaisesRegex(ValueError, "approval counts changed"):
            ad012._validate_ad010(rows)


if __name__ == "__main__":
    unittest.main()
