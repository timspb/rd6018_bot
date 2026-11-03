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

    def test_missing_live_session_cannot_be_misreported_as_retired(self):
        # Observed node104 hands_off state has an old D090 STARTED journal
        # but no active charge_session.json. Do not invent a tombstone to
        # satisfy historical D137 preflight.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / "state" / "charge_session.json").unlink()
            journal_before = (root / "D090_TRANSACTION.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "missing-session retirement record is not authentic"):
                self.capture(root)
            self.assertEqual((root / "D090_TRANSACTION.json").read_bytes(),
                             journal_before)

    def test_authentic_v2_retirement_without_session_is_observed_not_fabricated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / "state" / "charge_session.json").unlink()
            path = root / "state" / "session_recovery_quarantine.json"
            path.write_text(json.dumps({
                "owner": "runtime.charge.recovery_quarantine_journal",
                "schema_version": 2,
                "state": "retired",
                "quarantined": False,
                "retirement": {
                    "session_id": "s",
                    "confirmed_off_evidence": "off-verified",
                    "retired_utc": "2026-11-01T10:35:56Z",
                    "incident_id": "case-1",
                },
            }))
            original = {str(x.relative_to(root)):x.read_bytes()
                        for x in root.rglob("*") if x.is_file()}
            payload = self.capture(root)
            self.assertTrue(payload["retired_session"]["session_absent"])
            self.assertIsNone(payload["retired_session"]["session_sha256"])
            self.assertEqual(payload["retired_session"]["session_id"], "s")
            self.assertEqual(payload["retired_session"]["off_evidence"], "off-verified")
            self.assertEqual(original, {str(x.relative_to(root)):x.read_bytes()
                                        for x in root.rglob("*") if x.is_file()})
            self.assertEqual(payload["preimage_sha256"],self.capture(root)["preimage_sha256"])

    def test_missing_session_with_quarantined_or_unknown_retirement_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / "state" / "charge_session.json").unlink()
            path = root / "state" / "session_recovery_quarantine.json"
            for patch in ({"schema_version": 1, "state": "retired"},
                          {"schema_version": 2, "state": "retired", "quarantined": True},
                          {"schema_version": 2, "state": "retired", "quarantined": False}):
                data = {
                    "owner": "runtime.charge.recovery_quarantine_journal",
                    "schema_version": 2, "state": "retired",
                    "quarantined": False,
                    "retirement": {"session_id": "s",
                                   "confirmed_off_evidence": "off-verified",
                                   "retired_utc": "2026-11-01T10:35:56Z"},
                }
                data.update(patch)
                if patch.get("quarantined") is False:
                    data["retirement"]["confirmed_off_evidence"] = ""
                path.write_text(json.dumps(data))
                with self.subTest(patch=patch):
                    with self.assertRaises(ValueError):
                        self.capture(root)

    def test_quarantine_is_not_automatically_cleared_by_observer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            path = root / "state" / "session_recovery_quarantine.json"
            doc = json.loads(path.read_text(encoding="utf8"))
            doc["quarantined"] = True
            path.write_text(json.dumps(doc), encoding="utf8")
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "verified-OFF"):
                self.capture(root)
            self.assertEqual(path.read_bytes(), before)

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
