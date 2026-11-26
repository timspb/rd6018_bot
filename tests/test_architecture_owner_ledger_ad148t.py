import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/architecture/build_owner_ledger_ad148t.py"
spec = importlib.util.spec_from_file_location("ad148t", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AD148TLedgerTests(unittest.TestCase):
    def test_ad078_diagnostics_approval_binds_to_whole_file_table(self):
        event = next(e for e in mod._events() if e["stage"] == "AD078" and e["path"] == "runtime/charge/diagnostics.py")
        lines = (mod.ROOT / event["source"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[event["line"] - 1].split("|")[2].strip(), "APPROVE WITH NARROW EXCLUSION")
        self.assertTrue(lines[event["line"] - 1].startswith("| runtime/charge/diagnostics.py |"))
        self.assertEqual(event["status"], "APPROVED_PRIMARY_OWNER_ONLY")
        self.assertTrue(mod.validate_provenance(event))

    def test_ad078_recovery_session_approval_binds_to_whole_file_table(self):
        event = next(e for e in mod._events() if e["stage"] == "AD078" and e["path"] == "recovery_session.py")
        lines = (mod.ROOT / event["source"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[event["line"] - 1].split("|")[2].strip(), "APPROVE WITH NARROW EXCLUSION")
        self.assertTrue(lines[event["line"] - 1].startswith("| recovery_session.py |"))
        self.assertEqual(event["status"], "APPROVED_PRIMARY_OWNER_ONLY")
        self.assertTrue(mod.validate_provenance(event))

    def test_ad066_bounded_main_guard_module_approval_and_reader_function_scope(self):
        events = mod._events()
        approved = next(e for e in events if e["stage"] == "AD066" and e["path"])
        self.assertEqual(approved["path"], "runtime/charge/strategy/main_guard_admission.py")
        self.assertEqual(approved["owner"], "Safety Authority")
        self.assertEqual(approved["line"], 8)
        self.assertTrue(mod.validate_provenance(approved))
        stage = next(e for e in events if e["stage"] == "AD066" and not e["path"])
        self.assertEqual((stage["heading"], stage["line"]), ("Decision", 5))
        self.assertTrue(any(n["line"] == 9 and "read_canonical_session" in n["meaning"] for n in stage["scope_notes"]))
        self.assertFalse(any(e["path"] == "runtime/charge/persistence.py" for e in events))

    def test_ad076_later_file_hold_and_function_group_do_not_approve_persistence(self):
        events = mod._events()
        stage = next(e for e in events if e["stage"] == "AD076" and not e["path"])
        self.assertIn("NO_FILE_LEVEL_APPROVAL", stage["status"])
        self.assertEqual((stage["heading"], stage["line"]), ("Whole-file decisions", 5))
        self.assertTrue(any(n["line"] == 10 and "NO FILE-LEVEL APPROVAL" in n["meaning"] for n in stage["scope_notes"]))
        self.assertTrue(any(n["line"] == 31 and "read_canonical_session" in n["meaning"] for n in stage["scope_notes"]))
        self.assertTrue(mod.validate_provenance(stage))
        rows, counts = mod.build()
        by = {r["path"]: r for r in rows}
        self.assertEqual(by["runtime/charge/strategy/main_guard_admission.py"]["current_primary_approval"], "Safety Authority")
        self.assertEqual(by["runtime/charge/persistence.py"]["current_primary_approval"], "")
        self.assertEqual(by["runtime/charge/session.py"]["current_primary_approval"], "")
        self.assertEqual(counts["unique_current_primary_approvals"], 81)
        self.assertEqual(sum(1 for e in events if e["stage"] == "AD078" and e["status"] == "APPROVED_PRIMARY_OWNER_ONLY"), 6)
        coverage = next(x for x in mod.build_coverage(events) if x["stage"] == "AD076")
        self.assertEqual({x["path"] for x in coverage["whole_file_decisions"]}, {"runtime/charge/session.py", "runtime/charge/persistence.py"})
        self.assertTrue(all(x["decision"] == "NO FILE-LEVEL APPROVAL" for x in coverage["whole_file_decisions"]))
        self.assertEqual(len(coverage["scope_notes"]), 19)
        self.assertTrue(any("GuardedPhysicalResumePermit" in x["meaning"] for x in coverage["scope_notes"]))
        self.assertTrue(any("restore_session" in x["meaning"] for x in coverage["scope_notes"]))

    def test_ad062_section_is_deduplicated_but_both_path_events_remain(self):
        events = mod._events()
        paths = {e["path"] for e in events if e["stage"] == "AD062" and e["path"]}
        self.assertEqual(paths, {"runtime/charge/evidence/recovery_plateau_observer.py", "runtime/charge/evidence/recovery_plateau_policy.py"})
        coverage = next(x for x in mod.build_coverage(events) if x["stage"] == "AD062")
        self.assertEqual(coverage["sections"], [{"heading": "Decision", "line": 7}])
        rows, _ = mod.build()
        by = {r["path"]: r for r in rows}
        for path in paths:
            self.assertIn('"stage":"AD062"', by[path]["decision_history"])
            self.assertEqual(by[path]["current_primary_approval"], "Telemetry/Evidence")

    def test_ad144_first_stage_variables_is_reconfirmation_only(self):
        event = next(e for e in mod._events() if e["stage"] == "AD144" and e["path"] == "runtime/charge/evidence/first_stage_variables.py")
        self.assertEqual(event["owner"], "First Stage Evidence variables")
        self.assertEqual(event["status"], "RECONFIRMED")
        self.assertIn("near-target voltage margin and fallback MAIN tail-current threshold", event["scope"])
        self.assertTrue(mod.validate_provenance(event))
        rows, counts = mod.build()
        row = next(r for r in rows if r["path"] == event["path"])
        self.assertNotEqual(row["current_primary_approval"], "First Stage Evidence variables")
        self.assertIn('"status":"RECONFIRMED"', row["decision_history"])
        self.assertEqual(counts["unique_current_primary_approvals"], 81)

    def test_ad066_ad076_event_provenance_rejects_wrong_source_line(self):
        for stage in ("AD066", "AD076"):
            event = next(e.copy() for e in mod._events() if e["stage"] == stage and not e["path"])
            event["line"] += 1
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                mod.validate_provenance(event)

    def test_porcelain_z_rename_delete_and_untracked_paths(self):
        parsed = mod.parse_porcelain_z(
            b"R  renamed.py\0old.py\0 D deleted.py\0?? new file.py\0"
        )
        self.assertEqual(parsed["renamed.py"], "R ")
        self.assertEqual(parsed["old.py"], "R")
        self.assertEqual(parsed["deleted.py"], " D")
        self.assertEqual(parsed["new file.py"], "??")

    def test_empty_clean_git_status_is_valid(self):
        self.assertEqual(mod.parse_porcelain_z(b""), {})

    def test_porcelain_z_rejects_malformed_rename(self):
        with self.assertRaisesRegex(ValueError, "missing source path"):
            mod.parse_porcelain_z(b"R  renamed.py\0")

    def test_porcelain_rejects_unterminated_and_malformed_records(self):
        for data in (b"?? file", b"X", b"R  target\0"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                mod.parse_porcelain_z(data)

    def test_exact_git_path_state_for_tracked_untracked_rename_delete(self):
        self.assertEqual(mod.git_path_state(True, "", True), "tracked")
        self.assertEqual(mod.git_path_state(True, " M", True), "tracked_modified")
        self.assertEqual(mod.git_path_state(True, "R ", True), "renamed")
        self.assertEqual(mod.git_path_state(False, "R ", True), "renamed")
        self.assertEqual(mod.git_path_state(True, " D", False), "deleted")
        self.assertEqual(mod.git_path_state(False, "??", True), "untracked")
        self.assertEqual(mod.git_path_state(False, "", False), "absent")

    def test_adversarial_provenance_fault_injection(self):
        valid = next(e.copy() for e in mod._events() if e["stage"] == "AD145" and e["path"])
        self.assertTrue(mod.validate_provenance(valid))
        faults = []
        for field, value in (("owner", "WRONG OWNER"), ("stage", "AD146"),
                             ("path", "missing/path.py"), ("line", 999999),
                             ("source", "docs/RD6018_AD146_OPERATOR_PAUSE_APPLICATION_OWNER_2026-11-16.md"),
                             ("heading", "Unrelated heading")):
            bad = valid.copy(); bad[field] = value; faults.append(bad)
        for bad in faults:
            with self.subTest(fault=bad):
                with self.assertRaises(ValueError):
                    mod.validate_provenance(bad)

    def test_conflicting_approval_and_held_owner_override(self):
        a = {"stage":"AD056", "status":"APPROVED_PRIMARY_OWNER_ONLY", "owner":"Owner A"}
        b = {"stage":"AD057", "status":"APPROVED_PRIMARY_OWNER_ONLY", "owner":"Owner B"}
        with self.assertRaisesRegex(ValueError, "conflicting owner"):
            mod.current_owner([a, b])
        held = {"stage":"AD083", "status":"HELD_NO_FILE_LEVEL_APPROVAL", "owner":""}
        self.assertEqual(mod.current_owner([a, held]), "")

    def test_wrong_owner_row_injected_into_source_is_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            root = Path(td)
            source = root / "RD6018_AD145_fixture.md"
            source.write_text("# AD-145 fixture\n## Decision\n### Ownership\nWrong Owner owns it\n## Approved implementation\n`runtime/charge/evidence/manual_delta.py`\n", encoding="utf-8")
            event = {"source":source.name,"stage":"AD145","path":"runtime/charge/evidence/manual_delta.py","owner":"Manual Delta Evidence","status":"APPROVED_PRIMARY_OWNER_ONLY","line":6,"owner_line":4,"heading":"Approved implementation"}
            with self.assertRaisesRegex(ValueError, "owner not associated|unrelated subsection"):
                mod.validate_provenance(event, root)

    def test_deterministic_generation_and_expected_crosswalk(self):
        first, counts = mod.build()
        second, counts2 = mod.build()
        self.assertEqual((first, counts), (second, counts2))
        self.assertEqual(counts["AD012_paths"], 499)
        self.assertEqual(len(first), 500)
        by = {r["path"]: r for r in first}
        self.assertEqual(by["runtime/charge/restore_projection.py"]["current_primary_approval"], "")
        self.assertIn('"stage":"AD067"', by["runtime/charge/restore_projection.py"]["decision_history"])
        self.assertEqual(counts["AD056_AD057_decision_events"], 17)
        self.assertEqual(counts["AD142_AD146_new_approvals"], 6)
        self.assertEqual(counts["unique_current_primary_approvals"], 81)
        self.assertTrue(all(not r["resolved_final_owner"] for r in first))
        self.assertEqual(by["runtime/charge/diagnostics.py"]["current_primary_approval"], "Application")
        self.assertEqual(by["recovery_session.py"]["current_primary_approval"], "Recovery & Ownership")
        for path in ("runtime/charge/diagnostics.py", "recovery_session.py"):
            self.assertIn('"status":"APPROVED_PRIMARY_OWNER_ONLY"', by[path]["decision_history"])
            self.assertNotIn('"status":"FUNCTION_GROUP_ONLY"', by[path]["decision_history"])
        self.assertEqual(by["rd_managed_adoption.py"]["current_primary_approval"], "")
        self.assertIn('"status":"HELD_NO_FILE_LEVEL_APPROVAL"', by["rd_managed_adoption.py"]["decision_history"])
        self.assertIn('"stage":"AD057"', by["rd_managed_adoption.py"]["decision_history"])
        self.assertIn('"stage":"AD083"', by["rd_managed_adoption.py"]["decision_history"])
        self.assertTrue(by["application/manual_supervisor_use_case.py"]["current_primary_approval"])
        self.assertEqual(by["application/manual_supervisor_use_case.py"]["ad012_membership"], "AD012")
        self.assertIn(by["bot.py"]["git_status"], {"tracked", "tracked_modified"})

    def test_missing_source_fails_closed(self):
        with patch.object(mod, "CHRONOLOGY", Path("/missing/ad148s.md")):
            with self.assertRaises(FileNotFoundError):
                mod.build()

    def test_historical_artifact_bytes_unchanged_by_generation(self):
        before = [p.read_bytes() for p in (mod.AD010, mod.AD012, mod.AD014)]
        mod.build()
        self.assertEqual(before, [p.read_bytes() for p in (mod.AD010, mod.AD012, mod.AD014)])

    def test_report_has_no_hash_pinning_claims(self):
        rows, counts = mod.build()
        report = mod.render_report(rows, counts).casefold()
        self.assertNotIn("sha-256", report)
        self.assertNotIn("sha256", report)
        self.assertNotIn("hash pin", report)
        self.assertNotIn("integrity-pinned", report)
        self.assertIn("does not write", report)
        self.assertNotIn("hashlib", Path(mod.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
