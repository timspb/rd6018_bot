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
        finalization = (ROOT / "runtime/charge/restore_finalization.py").read_text()

        self.assertIn("host._session_restore_snapshot = RestoredSessionDocument.capture(document)", finalization)
        self.assertNotIn("_session_restore_document", persistence + base + continuation + finalization)
        self.assertIn("restore_controller_session(", base)
        self.assertIn("persist_restore=restore_session", base)
        self.assertIn("finish_session_restore(", continuation)
        self.assertIn("snapshot.document", continuation)
        self.assertIn("if GUARD_KEY in data:", persistence)
        self.assertNotIn("main_guard_restore_boundary", continuation)
        self.assertNotIn("def try_restore_session", production)

    def test_guard_journal_is_rejected_once_by_persistence_before_host_mutation(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        restore = persistence.split("def restore_session(", 1)[1].split("__all__", 1)[0]
        guard = restore.index("if GUARD_KEY in data:")
        first_mutation = restore.index("host._stage_tracking_enabled = False", guard)
        second_guard = restore.index("if GUARD_KEY in data:", guard + 1)
        self.assertLess(guard, second_guard)
        self.assertLess(second_guard, first_mutation)
        self.assertIn("read_guard(", restore[guard:second_guard])
        self.assertNotIn("read_guard(", restore[second_guard:first_mutation])

    def test_schema_assembly_and_atomic_completion_remain_single_owner(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        projection_owner = (ROOT / "runtime/charge/session_document_projection.py").read_text()
        atomic = (ROOT / "runtime/charge/session_atomic.py").read_text()
        writer = persistence.split("def save_session(", 1)[1].split("def mark_session_interrupted(", 1)[0]
        self.assertEqual(projection_owner.count("def project_session_document("), 1)
        self.assertEqual(projection_owner.count('"profile": host.battery_type'), 1)
        self.assertIn("data = complete_session_document(", projection_owner)
        self.assertIn("from runtime.charge.session_document_projection import (", persistence)
        self.assertIn("project_session_document,", persistence)
        self.assertNotIn("def project_session_document(", persistence)
        self.assertIn("atomic_session_write(", writer)
        self.assertIn("def complete_session_document(", atomic)


if __name__ == "__main__":
    unittest.main()
