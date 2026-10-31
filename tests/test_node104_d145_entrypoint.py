from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from tools import node104_d145_entrypoint as entrypoint


class D145D146EntrypointTests(unittest.TestCase):
    def test_canonical_profile_is_exactly_source_and_safety_pinned(self):
        path = entrypoint.default_profile()
        pin, preimage, record = entrypoint.load_pinned_profile(path)

        self.assertEqual(pin.source_sha, entrypoint.SOURCE_SHA)
        self.assertEqual(preimage, entrypoint.PREIMAGE_INVENTORY_SHA256)
        self.assertEqual(pin.firmware, "2.3-ha-canonical")
        self.assertEqual(pin.edge_lease_ttl_s, 900)
        self.assertEqual(pin.edge_renewal_s, 300)
        self.assertEqual(record["proof_collector_sha256"], entrypoint.D147_SHA)

    def test_profile_digest_mismatch_fails_before_profile_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_bytes(entrypoint.default_profile().read_bytes() + b" ")
            with self.assertRaisesRegex(entrypoint.d090.TransactionError, "digest"):
                entrypoint.load_pinned_profile(path)

    def test_profile_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.symlink_to(entrypoint.default_profile())
            with self.assertRaisesRegex(entrypoint.d090.TransactionError, "regular non-symlink"):
                entrypoint.load_pinned_profile(path)

    def test_current_profile_bytes_match_entrypoint_pin(self):
        path = entrypoint.default_profile()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(digest, entrypoint.PROFILE_SHA256)

    def test_builder_binds_software_release_to_existing_d090_owner(self):
        owner = entrypoint.build_owner(entrypoint.default_profile())
        self.assertIsInstance(owner, entrypoint.d090.D090Transaction)
        self.assertTrue(owner.software_release)
        self.assertEqual(owner.root, Path(entrypoint.release.ROOT))
        self.assertEqual(owner.pinned.source_sha, entrypoint.SOURCE_SHA)
        self.assertEqual(owner.preimage_inventory_sha256,
                         entrypoint.PREIMAGE_INVENTORY_SHA256)
        self.assertIsInstance(owner.service, entrypoint.d090.SystemdService)

    def test_cli_exposes_only_d145_transaction_phases(self):
        parser = entrypoint.make_parser()
        self.assertEqual(
            parser.parse_args(["prepare"]).phase,
            "prepare",
        )
        with self.assertRaises(SystemExit):
            parser.parse_args(["activate"])


if __name__ == "__main__":
    unittest.main()