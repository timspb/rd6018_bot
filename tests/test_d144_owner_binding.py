"""D144 production-binding contract; no node access or service changes."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

import tools.d144_owner_binding as binding


SOURCE = "d351c208cbf8666f881a4660df6a0b211170e857"
PREIMAGE = "f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c"


class D144OwnerBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="d144-binding-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.owner = object.__new__(binding.d090.D090Transaction)
        self.owner.root = self.root
        self.owner.offline = False
        self.owner.software_release = True
        self.owner.pinned = SimpleNamespace(source_sha=SOURCE)
        self.owner._lock_depth = 0
        self.owner.release_admission = lambda: None
        self.service = binding.d090.SystemdService()
        self.service.active = lambda: True
        self.service.layout_valid = lambda: True
        self.service.main_pid = lambda: 12345
        self.owner.service = self.service
        self.check = lambda: None
        self.owner.host_check = self.check
        self.gates = patch.multiple(binding.d090, production_host_check=self.check)
        self.gates.start()
        self.addCleanup(self.gates.stop)
        self.root_patch = patch.object(binding.d090.release, "ROOT", str(self.root))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_owner_lock_and_no_service_mutation(self):
        proof = {
            "preflight": "PASS_AT_OBSERVATION_ONLY",
            "candidate_identity_sha256": "a" * 64,
            "fresh_d091_off": True,
            "capacity_pass": True,
        }
        with patch.object(binding, "assess", return_value=proof) as observed:
            result = binding.prepare_only(
                self.owner, stage=self.root, source_sha=SOURCE,
                preimage_sha256=PREIMAGE, collector=self.root / "collector")
        self.assertEqual(result["status"], "PREPARE_ONLY_PASS")
        self.assertFalse(result["activation_authorized"])
        self.assertTrue((self.root / "D090_TRANSACTION.lock").is_file())
        self.assertEqual(observed.call_count, 1)
        self.assertFalse((self.root / "D144_TRANSACTION.json").exists())

    def test_wrong_source_fails_before_observation(self):
        with patch.object(binding, "assess") as observed:
            with self.assertRaises(binding.d090.TransactionError):
                binding.prepare_only(self.owner, stage=self.root, source_sha="b" * 40,
                    preimage_sha256=PREIMAGE, collector=self.root / "collector")
            observed.assert_not_called()

    def test_offline_owner_rejected(self):
        self.owner.offline = True
        with self.assertRaises(binding.d090.TransactionError):
            binding.prepare_only(self.owner, stage=self.root, source_sha=SOURCE,
                preimage_sha256=PREIMAGE, collector=self.root / "collector")

    def test_incomplete_combined_proof_refused(self):
        with patch.object(binding, "assess", return_value={"preflight": "BLOCKED"}):
            with self.assertRaises(binding.d090.TransactionError):
                binding.prepare_only(self.owner, stage=self.root, source_sha=SOURCE,
                    preimage_sha256=PREIMAGE, collector=self.root / "collector")


if __name__ == "__main__":
    unittest.main()
