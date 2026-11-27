"""B1061 D144: restored/contained != operationally ready; all owners remain closed."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.charge.persistence import begin_start_pending
from runtime.journal.recovery_quarantine import RecoveryQuarantineJournal
from tools.d144_owner_binding import _restored_quarantine_contained, d090
PhysicalOffProof = d090.release.PhysicalOffProof
MACHINE_ID = d090.release.MACHINE_ID


class RestoreOnlyProofTests(unittest.TestCase):
    def create(self, root):
        state = root / "state"
        state.mkdir()
        session = state / "charge_session.json"
        start = begin_start_pending({
            "stage": "Main Charge",
            "v2_trace_session_id": "s-b1061",
            "v2_battery_id": "Leoch_72Ah",
        }, transaction_id="tx-b1061", path=session)
        self.assertEqual(start.status.value, "COMMITTED")
        app = SimpleNamespace(charge_controller=SimpleNamespace(
            _v2_trace_session_id="s-b1061", _v2_battery_id="Leoch_72Ah"
        ))
        journal = RecoveryQuarantineJournal(state / "session_recovery_quarantine.json", app)
        journal.persist("start_enable_off_receipt_invalid")
        (root / "app").mkdir()
        (root / "app/bot.py").write_text("# immutable test fixture")
        (root / ".deploy_sha").write_text("old_sha\n")
        receipt={"source_sha":"old_sha","transaction":"tx-d144-24"}
        (root / "D144_INSTALLED_RELEASE_24.json").write_text(json.dumps(receipt))
        (root / "D144_TRANSACTION_24.json").write_text(json.dumps({
            "phase":"COMMITTED","slot":24,"transaction":"tx-d144-24",
            "release_identity":{"source_sha":"old_sha"},
        }))
        self.logs = "START_PENDING recovery quarantined: RuntimeError"
        class Service:
            def active(_): return True
            def main_pid(_): return 42
            def _run(_, *args):
                if "NRestarts" in args:return "0"
                if "ActiveEnterTimestamp" in args:return "2026-11-27 18:00:00"
                if "journalctl" in args:return self.logs
                raise AssertionError(args)
        owner = SimpleNamespace(root=root, pinned=SimpleNamespace(
            old_source_sha="old_sha"), service=Service())
        proof = PhysicalOffProof(
            captured_at_epoch=time.time(), host_machine_id=MACHINE_ID,
            service_main_pid=42, ha102_output_off=True,
            ha102_voltage_v=None, ha102_current_a=0.0,
            esp128_output_off=True, esp128_voltage_v=None,
            esp128_current_a=0.0, native_sensor_state_fresh=True,
            edge_lease_armed=False, edge_boot_quarantine=False,
            physical_node_owner_count=1, active_session=True,
            source_nonces=("source-a", "source-b")
        )
        return owner, proof, session, journal

    def evaluate(self, owner, proof):
        original_iterdir = Path.iterdir
        original_read_bytes = Path.read_bytes
        def iterdir(p):
            return iter([Path("/proc/42")]) if str(p)=="/proc" else original_iterdir(p)
        def read_bytes(p):
            if str(p)=="/proc/42/cmdline":
                return str(owner.root / "app/bot.py").encode() + b"\x00"
            return original_read_bytes(p)
        with patch.object(Path,"iterdir",iterdir), patch.object(Path,"read_bytes",read_bytes):
            return _restored_quarantine_contained(owner,evidence=lambda **kw: proof)

    def test_exact_quarantine_only_safe_restore(self):
        with tempfile.TemporaryDirectory() as td:
            owner, proof, session, journal = self.create(Path(td))
            before=(session.read_bytes(), (owner.root/"state/session_recovery_quarantine.json").read_bytes())
            self.assertTrue(self.evaluate(owner,proof))
            self.assertEqual(before,(session.read_bytes(),(owner.root/"state/session_recovery_quarantine.json").read_bytes()))

    def test_identity_and_live_polling_are_never_safe_restore(self):
        with tempfile.TemporaryDirectory() as td:
            owner, proof, session, journal = self.create(Path(td))
            self.logs="Start polling\nSTART_PENDING recovery quarantined"
            self.assertFalse(self.evaluate(owner,proof))
            self.logs="START_PENDING recovery quarantined"
            (owner.root/".deploy_sha").write_text("foreign\n")
            self.assertFalse(self.evaluate(owner,proof))
            (owner.root/".deploy_sha").write_text("old_sha\n")
            data=json.loads((owner.root/"state/session_recovery_quarantine.json").read_text())
            data["identity"]["session_id"]="foreign"
            (owner.root/"state/session_recovery_quarantine.json").write_text(json.dumps(data))
            self.assertFalse(self.evaluate(owner,proof))

    def test_physical_failure_is_not_stable(self):
        with tempfile.TemporaryDirectory() as td:
            owner, proof, session, journal = self.create(Path(td))
            from dataclasses import replace
            for failed in (
                replace(proof,ha102_output_off=False),
                replace(proof,edge_lease_armed=True),
                replace(proof,esp128_current_a=1.0),
            ):
                with self.subTest(failed=failed):
                    with self.assertRaises(Exception):
                        self.evaluate(owner,failed)
            self.assertFalse(self.evaluate(owner,replace(proof,service_main_pid=0)))
