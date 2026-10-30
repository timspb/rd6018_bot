"""D133 read-only baseline collector regression tests."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.d133_live_byte_baseline import inspect, tree_manifest


class LiveBaselineTests(unittest.TestCase):
    def make(self, root: Path):
        (root / "app").mkdir()
        (root / "app" / "bot.py").write_text("print('safe')", encoding="utf-8")
        (root / "d090").mkdir()
        (root / "d090" / "node104_d090_transaction.py").write_text("# local CLI", encoding="utf-8")
        (root / "state").mkdir()
        (root / ".deploy_sha").write_text("a" * 40 + "\n")
        (root / "D090_TRANSACTION.json").write_text(json.dumps({
            "phase": "STARTED", "transaction": "t1", "source_sha": "b" * 40
        }))
        (root / "state" / "charge_session.json").write_text(json.dumps({
            "state": "retired", "stage": "RETIRED", "session_id": "s1",
            "verified_off_transaction_id": "off1"
        }))
        (root / "state" / "session_recovery_quarantine.json").write_text(json.dumps({
            "quarantined": False,
            "retirement": {"session_id": "s1", "confirmed_off_evidence": "off1"}
        }))

    def test_readonly_stable_and_session_binding(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make(root)
            before = {p.relative_to(root).as_posix(): p.read_bytes()
                      for p in root.rglob("*") if p.is_file()}
            a, b = inspect(root), inspect(root)
            self.assertEqual(a, b)
            self.assertEqual(a["installed_app"]["files"], 1)
            self.assertTrue(a["session"]["retirement_evidence_matches"])
            self.assertTrue(a["session"]["retired"])
            self.assertFalse(a["deployment"]["candidate_inventory_present"])
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes()
                                      for p in root.rglob("*") if p.is_file()})

    def test_invalid_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make(root)
            (root / "app" / "link.py").symlink_to(root / "app" / "bot.py")
            with self.assertRaisesRegex(ValueError, "symlink"):
                tree_manifest(root / "app")

    def test_invalid_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make(root)
            (root / ".deploy_sha").write_text("not-a-sha")
            with self.assertRaisesRegex(ValueError, "legacy marker"):
                inspect(root)

    def test_mismatched_evidence_not_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make(root)
            p = root / "state" / "charge_session.json"
            state = json.loads(p.read_text())
            state["verified_off_transaction_id"] = "different"
            p.write_text(json.dumps(state))
            self.assertFalse(inspect(root)["session"]["retirement_evidence_matches"])


if __name__ == "__main__":
    unittest.main()
