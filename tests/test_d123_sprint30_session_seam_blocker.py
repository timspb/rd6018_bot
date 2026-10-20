"""Sprint 30 guard for the audited ordinary restore snapshot seam."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OrdinaryRestoreSnapshotOwnershipTests(unittest.TestCase):
    def test_canonical_restore_document_feeds_guard_and_trace_consumers(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        base = (ROOT / "charge_controller.py").read_text()
        production = (ROOT / "production_controller.py").read_text()

        self.assertIn("host._session_restore_document = dict(data)", persistence)
        self.assertIn("trace_document = dict(getattr(self, \"_session_restore_document\", {}))", base)
        self.assertIn("if GUARD_KEY in trace_document:", base)
        self.assertIn("guard, revision = read_guard(", base)
        self.assertNotIn("def try_restore_session", production)

    def test_schema_assembly_and_atomic_completion_remain_single_owner(self):
        persistence = (ROOT / "runtime/charge/persistence.py").read_text()
        atomic = (ROOT / "runtime/charge/session_atomic.py").read_text()
        self.assertEqual(persistence.count('"profile": host.battery_type'), 1)
        self.assertIn("data = complete_session_document(", persistence)
        self.assertIn("atomic_session_write(\n                session_file, data,", persistence)
        self.assertIn("def complete_session_document(", atomic)


if __name__ == "__main__":
    unittest.main()
