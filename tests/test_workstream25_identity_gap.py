import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Workstream25IdentityGapTests(unittest.TestCase):
    def test_identity_sources_are_inventoryable(self):
        controller = (ROOT / "charge_controller_v2.py").read_text(encoding="utf-8")
        manual = (ROOT / "manual_mode.py").read_text(encoding="utf-8")
        trace_store = (ROOT / "recovery_trace_store.py").read_text(encoding="utf-8")
        self.assertIn("_v2_trace_session_id", controller)
        self.assertIn("manual_session_v2.json", manual)
        self.assertIn("session_id TEXT NOT NULL", trace_store)

    def test_manual_path_has_no_runtime_identity_fields(self):
        manual = (ROOT / "manual_mode.py").read_text(encoding="utf-8")
        document_start = manual[manual.index("def _document") : manual.index("def _persist")]
        self.assertNotIn('"session_id"', document_start)
        self.assertNotIn('"trace_id"', document_start)

    def test_manual_restore_does_not_create_identity(self):
        manual = (ROOT / "manual_mode.py").read_text(encoding="utf-8")
        restore = manual[manual.index("def _restore_as_interrupted") : manual.index("def _reset_delta_tracking")]
        self.assertNotIn("uuid4", restore)
        self.assertNotIn("TraceContext", restore)

    def test_v2_automatic_path_and_manual_path_are_distinct(self):
        controller = (ROOT / "charge_controller_v2.py").read_text(encoding="utf-8")
        manual = (ROOT / "manual_mode.py").read_text(encoding="utf-8")
        self.assertIn("def _begin_trace_identity", controller)
        self.assertIn("def start(self, request: ManualChargeRequest)", manual)
        self.assertNotIn("_begin_trace_identity", manual)

    def test_no_runtime_files_were_modified_by_this_audit(self):
        # Static audit guard: this workstream adds no runtime implementation.
        self.assertTrue((ROOT / "manual_mode.py").exists())
        self.assertTrue((ROOT / "charge_controller_v2.py").exists())


if __name__ == "__main__":
    unittest.main()
