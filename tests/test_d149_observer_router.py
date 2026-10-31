import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import d149_observer_router as mod


class D149RouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d149-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "d147-proof").mkdir(mode=0o700)
        (self.root / "venv/bin").mkdir(parents=True)
        (self.root / "venv/bin/python").write_bytes(b"fake interpreter")
        self.old = self.root / "d147-proof/node104_d091_physical_proof_collector.py"
        self.new = self.root / "d147-proof/d148_recovery_d091_collector.py"
        self.old.write_bytes(b"old-read-only")
        self.new.write_bytes(b"new-recovery-capable")
        self.old.chmod(0o400)
        self.new.chmod(0o400)
        self.hash_old = patch.object(mod, "D147_SHA", hashlib.sha256(self.old.read_bytes()).hexdigest())
        self.hash_new = patch.object(mod, "D148_SHA", hashlib.sha256(self.new.read_bytes()).hexdigest())
        self.hash_old.start()
        self.hash_new.start()
        self.addCleanup(self.hash_old.stop)
        self.addCleanup(self.hash_new.stop)
        self.calls = []
        self.proof = {name: None for name in mod.release.PhysicalOffProof.__dataclass_fields__}
        self.proof.update({"source_nonces": ["nonce-a", "nonce-b"]})
        self.router = mod.ReadOnlyObserverRouter(self.root, runner=self.run_fake)

    def run_fake(self, cmd, env):
        self.calls.append((cmd, env))
        return json.dumps(self.proof)

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
        self.assertEqual(self.calls[-1][0][1], str(self.new))
        self.assertEqual(self.calls[-1][1]["D090_STATE_PRESERVING_RECOVERY"], "1")

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
