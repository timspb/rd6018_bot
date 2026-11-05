"""D137 regression tests: never run hardware or service operations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.d137_observed_preimage import observed_preimage
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import attach_guard, GUARD_KEY
import time


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

    def guarded_main_fixture(self, root):
        self.fixture(root)
        sid, bid, now = "session-main", "battery-65", time.time()
        doc={"stage":"Main Charge","profile":"EFB","ah_limit":65,
             "v2_authoritative":True,"v2_trace_session_id":sid,"v2_battery_id":bid}
        guard=MainCurrentGuard.start(session_id=sid,battery_id=bid,segment_id="main-1",
            capacity_ah=65,recipe_initial_current_a=6.5,now_s=now)
        guard,_=guard.observe(now_s=now,output_on=False,measured_current_a=0.0,
                              fresh=True,stage="MAIN",battery_id=bid)
        doc=attach_guard(doc,guard,now_s=now,expected_revision=0)
        (root/"state"/"charge_session.json").write_text(json.dumps(doc))
        (root/"state"/"session_recovery_quarantine.json").write_text(json.dumps({
            "owner":"runtime.charge.recovery_quarantine_journal","schema_version":2,
            "state":"retired","quarantined":False,"retirement":{
                "operator_id":"operator","session_id":"old-session",
                "confirmed_off_evidence":"off-receipt","retired_utc":"2026-11-05T00:00:00Z",
                "incident_id":"incident","incident_reason":"safe-off","battery_id":None}}))
        return doc

    def test_guarded_main_is_observed_and_byte_pinned_without_resume_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=self.guarded_main_fixture(root)
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result=self.capture(root)
            proof=result["preserved_guarded_main"]
            self.assertEqual(proof["session_id"],"session-main")
            self.assertEqual(proof["revision"],1)
            self.assertEqual(proof["guard_sha256"],original[GUARD_KEY]["sha256"])
            self.assertFalse(proof["automatic_resume_authorized"])
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_guarded_main_hash_revision_or_pending_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); good=self.guarded_main_fixture(root)
            path=root/"state"/"charge_session.json"; doc=json.loads(path.read_text())
            doc[GUARD_KEY]["sha256"]="0"*64; path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"guard failed integrity"):
                self.capture(root)
            doc=json.loads(json.dumps(good)); doc[GUARD_KEY]["revision"]=0
            path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"guard failed integrity"):
                self.capture(root)

    def test_guarded_main_quarantine_must_be_canonical_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.guarded_main_fixture(root)
            path=root/"state"/"session_recovery_quarantine.json"; doc=json.loads(path.read_text())
            doc["quarantined"]=True; path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"canonical clear quarantine"):
                self.capture(root)

    def historical_on_reconciliation(self, pid=1234, captured=None):
        now = time.time() if captured is None else captured
        return {
            "schema": "D142_VALIDATED_D091_OFF_V1", "captured_at_epoch": now,
            "service_main_pid": pid, "native_sensor_state_fresh": True,
            "ha102_output_off": True, "ha102_voltage_v": 0.0, "ha102_current_a": 0.0,
            "esp128_output_off": True, "esp128_voltage_v": 0.0, "esp128_current_a": 0.0,
            "edge_lease_armed": False, "edge_boot_quarantine": False,
            "physical_node_owner_count": 1, "active_session": True,
            "source_nonces": ["native-fresh-1", "ha-independent-1"],
        }

    def guarded_main_historical_on_fixture(self, root):
        self.fixture(root)
        sid, bid, now = "session-main", "battery-65", time.time()
        doc={"stage":"Main Charge","profile":"EFB","ah_limit":65,
             "v2_authoritative":True,"v2_trace_session_id":sid,"v2_battery_id":bid}
        guard=MainCurrentGuard.start(session_id=sid,battery_id=bid,segment_id="main-1",
            capacity_ah=65,recipe_initial_current_a=6.5,now_s=now)
        guard,_=guard.observe(now_s=now,output_on=True,measured_current_a=1.0,
                              fresh=True,stage="MAIN",battery_id=bid)
        doc=attach_guard(doc,guard,now_s=now,expected_revision=0)
        (root/"state"/"charge_session.json").write_text(json.dumps(doc))
        (root/"state"/"session_recovery_quarantine.json").write_text(json.dumps({
            "owner":"runtime.charge.recovery_quarantine_journal","schema_version":2,
            "state":"retired","quarantined":False,"retirement":{
                "operator_id":"operator","session_id":"old-session",
                "confirmed_off_evidence":"off-receipt","retired_utc":"2026-11-05T00:00:00Z",
                "incident_id":"incident","incident_reason":"safe-off","battery_id":None}}))

    def test_historical_guard_on_requires_fresh_d091_off_and_is_byte_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.guarded_main_historical_on_fixture(root)
            with self.assertRaisesRegex(ValueError, "state-preserving OFF"):
                self.capture(root)
            physical = self.historical_on_reconciliation()
            original=(root/"state"/"charge_session.json").read_bytes()
            real_read=Path.read_bytes
            def fake_argv(path):
                if str(path)=="/proc/1234/cmdline":
                    return str(root/"app"/"bot.py").encode()+bytes([0])
                return real_read(path)
            with patch.object(Path,"read_bytes",fake_argv):
                result=observed_preimage(root,pid=1234,physical_off_reconciliation=physical)
            preserved=result["preserved_guarded_main"]
            self.assertTrue(preserved["automatic_resume_authorized"] is False)
            self.assertTrue(preserved["last_output_on"])
            self.assertEqual(preserved["physical_off_reconciliation"],physical)
            self.assertEqual((root/"state"/"charge_session.json").read_bytes(),original)

    def test_historical_guard_on_rejects_stale_or_wrong_pid_d091_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.guarded_main_historical_on_fixture(root)
            for proof in (self.historical_on_reconciliation(captured=time.time()-9),
                          self.historical_on_reconciliation(pid=999)):
                with self.subTest(proof=proof):
                    original=Path.read_bytes
                    def fake_argv(path):
                        if str(path)=="/proc/1234/cmdline":
                            return str(root/"app"/"bot.py").encode()+bytes([0])
                        return original(path)
                    with patch.object(Path,"read_bytes",fake_argv), self.assertRaisesRegex(
                            ValueError,"state-preserving OFF"):
                        observed_preimage(root,pid=1234,physical_off_reconciliation=proof)


if __name__=="__main__":
    unittest.main()
