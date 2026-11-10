from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.d138_candidate_preflight import inspect_candidate

SOURCE="d351c208cbf8666f881a4660df6a0b211170e857"
PREIMAGE="f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c"


class D138CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"live"
        self.stage=Path(self.tmp.name)/"stage"
        self.root.mkdir()
        (self.stage/"tree").mkdir(parents=True)
        f=self.stage/"tree"/"bot.py"
        f.write_bytes(b"candidate")
        f.chmod(0o644)
        entry={"path":"bot.py","sha256":hashlib.sha256(b"candidate").hexdigest(),
               "size":9,"mode":0o644}
        (self.stage/"RELEASE_MANIFEST.json").write_text(json.dumps({
            "schema":"D138_STAGED_SOURCE_V1","source_sha":SOURCE,
            "source_archive_sha256":"a"*64,"files":1,"manifest_entries":[entry]}))
        (self.stage/"venv"/"bin").mkdir(parents=True)
        (self.stage/"venv"/"bin"/"python").write_text("fixture")

    def run_preflight(self, *, preimage=PREIMAGE, observed_record=None, installed=True):
        def subproc(cmd,**kw):
            if "-m" in cmd:return SimpleNamespace(returncode=0,stdout="No broken requirements found.")
            return SimpleNamespace(returncode=0,stdout="(3, 11)\n")
        actual=observed_record or {"preimage_sha256":preimage}
        with patch("tools.d138_candidate_preflight.observed_preimage",return_value=actual), \
             patch("tools.d138_candidate_preflight.inventory_venv",return_value={"regular_files":101,"tree_sha256":"b"*64}), \
             patch("tools.d138_candidate_preflight.subprocess.run",side_effect=subproc), \
             patch("tools.d138_candidate_preflight.shutil.disk_usage",return_value=SimpleNamespace(free=500*1024*1024)):
            return inspect_candidate(root=self.root,stage=self.stage,pid=123,
                                     source_sha=SOURCE,preimage_sha256=PREIMAGE)

    def test_real_d137_v2_retirement_without_session_flows_to_d138(self):
        # End-to-end OFF-history *state* observation, not physical OFF proof.
        # The real node104 has a v2 retired quarantine, no charge session,
        # and a historical D090 STARTED journal.
        from tools.d137_observed_preimage import observed_preimage
        from types import SimpleNamespace
        (self.root / "app").mkdir()
        (self.root / "app" / "bot.py").write_text("fixture")
        (self.root / "venv" / "bin").mkdir(parents=True)
        (self.root / "venv" / "bin" / "python").write_text("fixture")
        (self.root / "state").mkdir()
        (self.root / "state" / "session_recovery_quarantine.json").write_text(
            json.dumps({
                "owner": "runtime.charge.recovery_quarantine_journal",
                "schema_version": 2, "state": "retired", "quarantined": False,
                "retirement": {
                    "session_id": "prior-session",
                    "confirmed_off_evidence": "old-off-evidence",
                    "retired_utc": "2026-11-01T10:35:56Z",
                },
            })
        )
        (self.root / "D090_TRANSACTION.json").write_text(json.dumps({
            "phase": "STARTED",
            "transaction": "legacy",
            "source_sha": "930239c670899e14ccb09154d99baf77df90da10",
        }))
        (self.root / ".deploy_sha").write_text("58321a866dd68195bf8264d1d9ebe7c18a60748f")
        original_read = Path.read_bytes
        def proc_and_disk_read(path):
            if str(path) == "/proc/123/cmdline":
                return str(self.root / "app" / "bot.py").encode() + bytes([0])
            return original_read(path)
        def proc_call(cmd, **kwargs):
            if "-m" in cmd:
                return SimpleNamespace(returncode=0, stdout="No broken requirements found.")
            return SimpleNamespace(returncode=0, stdout="(3, 11)\n")
        with patch.object(Path, "read_bytes", proc_and_disk_read), \
             patch("tools.d138_candidate_preflight.inventory_venv",
                   return_value={"regular_files": 101, "tree_sha256": "b"*64}), \
             patch("tools.d138_candidate_preflight.subprocess.run", side_effect=proc_call), \
             patch("tools.d138_candidate_preflight.shutil.disk_usage",
                   return_value=SimpleNamespace(free=500*1024*1024)):
            observed = observed_preimage(self.root, pid=123)
            self.assertTrue(observed["retired_session"]["session_absent"])
            self.assertEqual(observed["retired_session"]["session_id"], "prior-session")
            result = inspect_candidate(
                root=self.root, stage=self.stage, pid=123,
                source_sha=SOURCE,
                preimage_sha256=observed["preimage_sha256"],
            )
        self.assertEqual(result["status"], "SOURCE_AND_VENV_PREPARED_NOT_ACTIVATED")
        self.assertFalse(result["admitted_for_activation"])
        self.assertTrue((self.root / "D090_TRANSACTION.json").is_file())
        self.assertFalse((self.root / "state" / "charge_session.json").exists())

    def test_prepared_is_never_actuation_admission(self):
        result=self.run_preflight()
        self.assertFalse(result["admitted_for_activation"])
        self.assertEqual(result["status"],"SOURCE_AND_VENV_PREPARED_NOT_ACTIVATED")
        self.assertEqual(result["source_files"],1)

    def test_active_orphan_quarantine_is_bound_into_candidate_identity(self):
        first = {
            "preimage_sha256": PREIMAGE,
            "preserved_quarantine": {
                "incident_id": "acb9302c-8925-47b1-be48-15a38dc01b4a",
                "incident_utc": "2026-11-10T05:09:53.917914+00:00",
                "reason": "main_guard_current_ocp_transaction_unconfirmed:readback_mismatch",
                "session_id": "session-a",
                "battery_id": "adhoc:EFB:60:38426001",
                "session_absent": True,
                "quarantine_sha256": "a" * 64,
            },
        }
        second = {
            "preimage_sha256": PREIMAGE,
            "preserved_quarantine": {
                **first["preserved_quarantine"],
                "incident_id": "b" * 36,
                "quarantine_sha256": "b" * 64,
            },
        }
        one = self.run_preflight(observed_record=first)
        two = self.run_preflight(observed_record=second)
        self.assertEqual(one["preserved_quarantine"], first["preserved_quarantine"])
        self.assertNotEqual(one["candidate_identity_sha256"], two["candidate_identity_sha256"])

    def test_guarded_candidate_identity_is_stable_across_fresh_d091_proofs(self):
        first={"schema":"D142_VALIDATED_D091_OFF_V1","captured_at_epoch":1,
               "source_nonces":["native-1","ha-1"]}
        second={"schema":"D142_VALIDATED_D091_OFF_V1","captured_at_epoch":2,
                "source_nonces":["native-2","ha-2"]}
        records=[{"preimage_sha256":PREIMAGE,"preserved_guarded_main":{
                      "session_id":"session","revision":481,
                      "physical_off_reconciliation":proof}}
                 for proof in (first,second)]
        results=[self.run_preflight(observed_record=record) for record in records]
        self.assertEqual(results[0]["candidate_identity_sha256"],
                         results[1]["candidate_identity_sha256"])
        self.assertNotEqual(results[0]["preserved_guard"],results[1]["preserved_guard"])

    def test_live_preimage_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"preimage drift"):
            self.run_preflight(preimage="c"*64)

    def test_source_byte_corruption_fails_closed(self):
        (self.stage/"tree"/"bot.py").write_text("tampered")
        with self.assertRaisesRegex(ValueError,"byte/mode mismatch"):
            self.run_preflight()

    def test_missing_venv_fails_closed(self):
        (self.stage/"venv"/"bin"/"python").unlink()
        with self.assertRaisesRegex(ValueError,"environment incomplete"):
            self.run_preflight()


if __name__=="__main__":
    unittest.main()
