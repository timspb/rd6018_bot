"""Sprint 30 guard for the audited ordinary restore snapshot seam."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OrdinaryRestoreSnapshotOwnershipTests(unittest.TestCase):
    def test_canonical_restore_snapshot_is_typed_and_consumed_by_session_owner(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        base = (ROOT / "charge_controller.py").read_text()
        production = (ROOT / "production_controller.py").read_text()
        continuation = (ROOT / "runtime/charge/session_continuation_restore.py").read_text()

        self.assertIn("host._session_restore_snapshot = RestoredSessionDocument.capture(data)", persistence)
        self.assertNotIn("_session_restore_document", persistence + base + continuation)
        self.assertIn("finish_session_restore(", base)
        self.assertIn("snapshot.document", continuation)
        self.assertIn("if GUARD_KEY in data:", persistence)
        self.assertNotIn("main_guard_restore_boundary", continuation)
        self.assertNotIn("def try_restore_session", production)

    def test_guard_journal_is_rejected_once_by_persistence_before_host_mutation(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        guard = persistence.index("if GUARD_KEY in data:")
        first_mutation = persistence.index("host._stage_tracking_enabled = False", guard)
        self.assertLess(guard, first_mutation)
        self.assertEqual(persistence.count("if GUARD_KEY in data:"), 1)

    def test_schema_assembly_and_atomic_completion_remain_single_owner(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        atomic = (ROOT / "runtime/charge/session_atomic.py").read_text()
        self.assertEqual(persistence.count('"profile": host.battery_type'), 1)
        self.assertIn("data = complete_session_document(", persistence)
        self.assertIn("atomic_session_write(\n                session_file, data,", persistence)
        self.assertIn("def complete_session_document(", atomic)


if __name__ == "__main__":
    unittest.main()
