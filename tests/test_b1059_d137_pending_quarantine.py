"""B1059: D137 accepts only a byte-preserved quarantined START + fresh D142 OFF."""
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.charge.persistence import begin_start_pending
from runtime.journal.recovery_quarantine import RecoveryQuarantineJournal
from tools.d137_observed_preimage import observed_preimage


class PendingD137Tests(unittest.TestCase):
    def fixture(self, root: Path):
        (root / "app").mkdir()
        (root / "app" / "bot.py").write_text("print('production fixture')\n")
        (root / "venv/bin").mkdir(parents=True)
        (root / "venv/bin/python").write_text("venv fixture")
        state = root / "state"
        state.mkdir()
        (root / "D090_TRANSACTION.json").write_text(
            json.dumps({"phase": "STARTED", "transaction": "immutable_legacy"})
        )
        (root / ".deploy_sha").write_text("a"*40+"\n")
        path = state / "charge_session.json"
        qpath = state / "session_recovery_quarantine.json"
        app = type("App", (), {})()
        app.charge_controller = type("Ctrl", (), {
            "_v2_trace_session_id": "s-b1059", "_v2_battery_id": "Leoch_72Ah"
        })()
        journal = RecoveryQuarantineJournal(qpath, app)
        journal.persist("start_enable_off_receipt_invalid")
        envelope = begin_start_pending({
            "stage": "Main Charge",
            "v2_trace_session_id": "s-b1059",
            "v2_battery_id": "Leoch_72Ah",
            "output_intent": "on",
        }, transaction_id="pending-b1059", path=path)
        self.assertEqual(envelope.status.value, "COMMITTED")
        return path, qpath

    def proof(self, *, pid=1234, **updates):
        data = dict(schema="D142_VALIDATED_D091_OFF_V1",
            captured_at_epoch=time.time(), service_main_pid=pid,
            native_sensor_state_fresh=True, ha102_output_off=True,
            ha102_current_a=0.0, esp128_output_off=True,
            esp128_current_a=0.0, edge_lease_armed=False,
            edge_boot_quarantine=False, physical_node_owner_count=1,
            active_session=True, source_nonces=["native-a", "ha-b"])
        data.update(updates)
        return data

    def capture(self, root, proof):
        original = Path.read_bytes
        def fake_proc(path):
            if str(path).replace("\\", "/") == "/proc/1234/cmdline":
                return str(root / "app/bot.py").encode() + b"\x00"
            return original(path)
        with patch.object(Path, "read_bytes", fake_proc):
            return observed_preimage(
                root, pid=1234, physical_off_reconciliation=proof
            )

    def test_valid_pending_exact_bytes_survive_and_identity_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session, journal = self.fixture(root)
            old = (session.read_bytes(), journal.read_bytes())
            first = self.capture(root, self.proof())
            second = self.capture(root, self.proof(source_nonces=["native-c", "ha-d"]))
            self.assertEqual(first["preimage_sha256"], second["preimage_sha256"])
            binding = first["preserved_quarantine"]
            self.assertEqual(binding["pending_sha256"], hashlib.sha256(old[0]).hexdigest())
            self.assertEqual(binding["quarantine_sha256"], hashlib.sha256(old[1]).hexdigest())
            self.assertEqual(binding["pending_transaction_id"], "pending-b1059")
            self.assertFalse(binding["automatic_resume_authorized"])
            self.assertFalse(binding["session_absent"])
            self.assertIsNone(first["retired_session"])
            self.assertEqual((session.read_bytes(), journal.read_bytes()), old)

    def test_missing_or_unsafe_physical_proof_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session, journal = self.fixture(root)
            old = (session.read_bytes(), journal.read_bytes())
            cases = (None,
                self.proof(edge_lease_armed=True),
                self.proof(esp128_output_off=False),
                self.proof(ha102_current_a=1.0),
                self.proof(source_nonces=["same", "same"]),
                self.proof(captured_at_epoch=time.time()-120),
                self.proof(service_main_pid=999),
                self.proof(active_session=False))
            for evidence in cases:
                with self.subTest(proof=evidence):
                    with self.assertRaisesRegex(ValueError, "fresh D142 OFF proof"):
                        self.capture(root, evidence)
            self.assertEqual((session.read_bytes(), journal.read_bytes()), old)

    def test_unrelated_quarantine_and_prior_session_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session, journal = self.fixture(root)
            actual = json.loads(journal.read_text())
            actual["identity"]["session_id"] = "foreign"
            journal.write_text(json.dumps(actual))
            with self.assertRaisesRegex(ValueError, "exact identity"):
                self.capture(root, self.proof())
            actual["identity"]["session_id"] = "s-b1059"
            journal.write_text(json.dumps(actual))
            # A pending START with previous committed bytes is not a release bypass.
            doc = json.loads(session.read_text())
            doc["start_transaction_pending_v1"]["previous_exists"] = True
            session.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "exact identity"):
                self.capture(root, self.proof())
