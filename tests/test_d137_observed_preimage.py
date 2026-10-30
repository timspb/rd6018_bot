"""D137 regression tests: never run hardware or service operations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.d137_observed_preimage import observed_preimage


class D137Tests(unittest.TestCase):
    def fixture(self, root):
        (root / "app").mkdir()
        (root / "app" / "bot.py").write_text("print('fixture')")
        (root / "venv" / "bin").mkdir(parents=True)
        (root / "venv" / "bin" / "python").write_text("venv fixture")
        state = root / "state"
        state.mkdir()
        (state / "charge_session.json").write_text(json.dumps({
            "state":"retired","stage":"RETIRED","session_id":"s",
            "verified_off_transaction_id":"off-verified"}))
        (state / "session_recovery_quarantine.json").write_text(json.dumps({
            "quarantined":False,
            "retirement":{"session_id":"s","confirmed_off_evidence":"off-verified"}}))
        (root / "D090_TRANSACTION.json").write_text(json.dumps({
            "phase":"STARTED","transaction":"legacy"}))
        (root / ".deploy_sha").write_text("a"*40+"\n")

    def capture(self, root):
        original = Path.read_bytes
        def fake_argv(path):
            if str(path)=="/proc/1234/cmdline":
                return str(root / "app" / "bot.py").encode()+bytes([0])
            return original(path)
        with patch.object(Path, "read_bytes", fake_argv):
            return observed_preimage(root, pid=1234)

    def test_observed_only_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            before = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result = self.capture(root)
            self.assertEqual(result["phase"],"OBSERVED_PREIMAGE")
            self.assertIsNone(result["candidate"])
            self.assertFalse(result["admitted"])
            self.assertFalse(result["d090"]["candidate_inventory_present"])
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob("*") if p.is_file()})
            self.assertEqual(result["preimage_sha256"],self.capture(root)["preimage_sha256"])

    def test_mismatched_off_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            state=root/"state"/"charge_session.json"
            doc=json.loads(state.read_text())
            doc["verified_off_transaction_id"]="other"
            state.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"verified-OFF"):
                self.capture(root)

    def test_legacy_inventory_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            p=root/"D090_TRANSACTION.json"
            doc=json.loads(p.read_text())
            doc["candidate_inventory"]={}
            p.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"unexpected historical"):
                self.capture(root)

    def test_app_change_changes_composite_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            first=self.capture(root)["preimage_sha256"]
            (root/"app"/"bot.py").write_text("modified")
            self.assertNotEqual(first,self.capture(root)["preimage_sha256"])


if __name__=="__main__":
    unittest.main()
