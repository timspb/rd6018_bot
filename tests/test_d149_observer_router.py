import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import d149_observer_router as mod

REAL_D151_SHA = mod.D151_SHA


class D149RouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d149-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "d147-proof").mkdir(mode=0o700)
        (self.root / "venv/bin").mkdir(parents=True)
        (self.root / "venv/bin/python").write_bytes(b"fake interpreter")
        self.old = self.root / "d147-proof/node104_d091_physical_proof_collector.py"
        self.new = self.root / "d147-proof/d150_poststart_d091_collector.py"
        self.guarded = self.root / "d147-proof/d151_software_release_d091_collector.py"
        self.old.write_bytes(b"old-read-only")
        self.new.write_bytes(b"new-recovery-capable")
        self.guarded.write_bytes(b"guarded-tripped-off-only")
        self.old.chmod(0o400)
        self.new.chmod(0o400)
        self.guarded.chmod(0o400)
        self.hash_old = patch.object(mod, "D147_SHA", hashlib.sha256(self.old.read_bytes()).hexdigest())
        self.hash_new = patch.object(mod, "D150_SHA", hashlib.sha256(self.new.read_bytes()).hexdigest())
        self.hash_guarded = patch.object(
            mod, "D151_SHA", hashlib.sha256(self.guarded.read_bytes()).hexdigest()
        )
        self.hash_old.start()
        self.hash_new.start()
        self.hash_guarded.start()
        self.addCleanup(self.hash_old.stop)
        self.addCleanup(self.hash_new.stop)
        self.addCleanup(self.hash_guarded.stop)
        self.calls = []
        self.proof = {name: None for name in mod.release.PhysicalOffProof.__dataclass_fields__}
        self.proof.update({"source_nonces": ["nonce-a", "nonce-b"]})
        self.router = mod.ReadOnlyObserverRouter(self.root, runner=self.run_fake)

    def run_fake(self, cmd, env):
        self.calls.append((cmd, env))
        return json.dumps(self.proof)

    def test_d151_pin_matches_existing_readonly_d091_source(self):
        source = Path(__file__).resolve().parents[1] / "tools/node104_d091_physical_proof_collector.py"
        # D151 pins the byte-for-byte CRLF collector deployed on node104.
        # GitHub Linux checkout normalizes tracked Python sources to LF;
        # reconstruct the deployed CRLF bytes for the immutable pin check.
        source_lf = source.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(source_lf.replace(b"\n", b"\r\n")).hexdigest(), REAL_D151_SHA)

    def test_old_before_stop_only(self):
        value = self.router()
        self.assertEqual(value.source_nonces, ("nonce-a", "nonce-b"))
        self.assertEqual(self.calls[-1][0][1], str(self.old))
        self.assertNotIn("D090_STATE_PRESERVING_RECOVERY", self.calls[-1][1])
        self.assertEqual(self.router.calls, 1)

    def test_new_when_stopped_or_started(self):
        for phase in ("STOPPED", "POST_START"):
            self.router.select(phase)
            self.router()
            self.assertEqual(self.calls[-1][0][1], str(self.new))
            self.assertNotIn("D090_STATE_PRESERVING_RECOVERY", self.calls[-1][1])

    def test_recovery_has_explicit_mode(self):
        self.router.select("RECOVERY")
        self.router()
        self.assertEqual(self.calls[-1][0][1], str(self.guarded))
        self.assertEqual(self.calls[-1][1]["D090_STATE_PRESERVING_RECOVERY"], "1")

    def test_guarded_main_preservation_uses_recovery_proof_on_every_phase(self):
        router=mod.ReadOnlyObserverRouter(self.root,runner=self.run_fake,
                                           state_preserving_recovery=True)
        for phase in ("PRE_STOP","STOPPED","POST_START"):
            router.select(phase); router()
            expected=self.guarded
            self.assertEqual(self.calls[-1][0][1],str(expected))
            self.assertEqual(self.calls[-1][1]["D090_STATE_PRESERVING_RECOVERY"],"1")

    def test_sha_mismatch_refuses_without_collecting(self):
        self.old.chmod(0o600)
        self.old.write_bytes(b"changed")
        self.old.chmod(0o400)
        with self.assertRaises(mod.ObserverRouteError):
            self.router()
        self.assertEqual(self.calls, [])

    def test_unreviewed_phase_fails_closed(self):
        with self.assertRaises(mod.ObserverRouteError):
            self.router.select("UNEXPECTED")
        self.assertEqual(self.router.phase, "PRE_STOP")

    def test_duplicate_nonces_rejected(self):
        self.proof["source_nonces"] = ["same", "same"]
        with self.assertRaises(mod.ObserverRouteError):
            self.router()
        self.assertEqual(self.router.calls, 0)

    def test_unexpected_schema_rejected(self):
        self.proof["unexpected"] = True
        with self.assertRaises(mod.ObserverRouteError):
            self.router()

    def test_symlinked_collector_denied(self):
        self.old.unlink()
        self.old.symlink_to(self.new)
        with self.assertRaises(mod.ObserverRouteError):
            self.router()

    def test_inaccessible_runtime_fails_closed(self):
        (self.root / "venv/bin/python").unlink()
        with self.assertRaises(mod.ObserverRouteError):
            self.router()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
