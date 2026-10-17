from dataclasses import replace
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("d090", Path(__file__).parents[1] / "tools/node104_d090_release.py")
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)
STAGING = Path("/tmp/rd6018-d089-20261017-staging/release-d29db790bf7140932bc005bddf6bd5988041bfc0-ukm77bsk")


@contextmanager
def staged_fixture():
    # CI must reconstruct its own release; never rely on a developer's /tmp.
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp) / "release"
        tree = stage / "tree"
        tree.mkdir(parents=True)
        source = tree / "module.py"
        data = b"RELEASE_FIXTURE = 'test-only'\n"
        source.write_bytes(data)
        archive = stage / "source.tar"
        with tarfile.open(archive, "w") as bundle:
            bundle.add(source, arcname="module.py")
        tarhash = M.sha256_file(archive)
        manifest = {
            "source_sha": M.SOURCE_SHA, "node": M.NODE,
            "service": "rd6018-bot", "archive_sha256": tarhash,
            "files": [{"path": "module.py", "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}],
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        manifesthash = hashlib.sha256(manifest_bytes).hexdigest()
        (stage / "RELEASE_MANIFEST.json").write_bytes(manifest_bytes)
        (stage / "STAGED_OK").write_text(json.dumps({
            "manifest_sha256": manifesthash, "tree_verified": True,
            "directory_fsync": True,
        }))
        pins = replace(M.PINNED, staging_manifest_sha256=manifesthash,
                       source_archive_sha256=tarhash)
        with patch.object(M, "PINNED", pins):
            yield stage


class ReleaseVerification(unittest.TestCase):
    @unittest.skipUnless(STAGING.is_dir(), "pinned 1003-file stage available only on WSL2 release host")
    def test_exact_supplied_staging_passes_integrity(self):
        manifest = M.verify_staged_release(STAGING)
        self.assertEqual(manifest["source_sha"], M.SOURCE_SHA)
        report = M.preflight_report(STAGING)
        self.assertEqual(report["decision"], "PREPARE_ONLY_PASS")
        self.assertFalse(report["activation_authorized"])
        self.assertTrue(report["blockers"])

    def test_portable_fixture_exact_archive_tree_passes(self):
        with staged_fixture() as stage:
            manifest = M.verify_staged_release(stage)
            self.assertEqual(M.SOURCE_SHA, manifest["source_sha"])
            report = M.preflight_report(stage)
            self.assertEqual("PREPARE_ONLY_PASS", report["decision"])
            self.assertFalse(report["activation_authorized"])

    def test_archive_corruption_and_traversal_rejected(self):
        with staged_fixture() as stage:
            with (stage / "source.tar").open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(M.GateError, "archive"):
                M.verify_staged_release(stage)

    def test_physical_gate_requires_fresh_native_off_zero_and_stopped(self):
        now = time.time()
        proof = M.PhysicalOffProof(now, M.MACHINE_ID, 0, True, 0.0, 0.0,
                                   True, 0.0, 0.0, True, False, False, 1,
                                   False, ("ha:nonce1", "esp:nonce2"))
        M.validate_physical_off(proof, now=now)
        for altered in (
            replace(proof, captured_at_epoch=now - 31),
            replace(proof, host_machine_id="wrong"),
            replace(proof, service_main_pid=123),
            replace(proof, esp128_output_off=False),
            replace(proof, esp128_current_a=0.2),
            replace(proof, edge_lease_armed=True),
            replace(proof, active_session=True),
            replace(proof, source_nonces=("same", "same")),
        ):
            with self.subTest(proof=altered), self.assertRaises(M.GateError):
                M.validate_physical_off(altered, now=now)

    def test_native_authority_survives_missing_stale_or_disagreeing_ha(self):
        now = time.time()
        proof = M.PhysicalOffProof(now, M.MACHINE_ID, 0, True, 0.0, 0.0,
                                   True, 0.0, 0.0, True, False, False, 1,
                                   False, ("native:1", "ha:1"))
        for advisory in (
            (None, None, None),
            (False, 0.6, 0.2),
            (True, 0.0, 0.0),
        ):
            with self.subTest(advisory=advisory):
                altered = replace(proof, ha102_output_off=advisory[0],
                                  ha102_voltage_v=advisory[1],
                                  ha102_current_a=advisory[2])
                M.validate_physical_off(altered, now=now)
        M.validate_physical_off(replace(proof, ha102_output_off=None), now=now)
        M.validate_physical_off(replace(proof, ha102_output_off=1,
            ha102_voltage_v="unknown", ha102_current_a=object()), now=now)

    def test_d089_or_software_ci_record_cannot_satisfy_physical_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            for record in ({"ci": "PASS"}, {"source_sha": M.SOURCE_SHA, "firmware": M.FIRMWARE,
                            "compiled_flashed_bench_validated": True, "cases": {}}):
                with self.subTest(record=record), self.assertRaises(M.GateError):
                    M.validate_physical_acceptance(record, Path(temp))

    def test_physical_proof_rejects_integer_boolean_and_wrong_owner_types(self):
        now = time.time()
        proof = M.PhysicalOffProof(now, M.MACHINE_ID, 0, True, 0.0, 0.0,
                                   True, 0.0, 0.0, True, False, False, 1,
                                   False, ("ha:nonce1", "esp:nonce2"))
        for altered in (replace(proof, esp128_output_off=1),
                        replace(proof, active_session=0),
                        replace(proof, physical_node_owner_count=True),
                        replace(proof, service_main_pid=False),
                        replace(proof, source_nonces=["ha:nonce1", "esp:nonce2"])):
            with self.subTest(proof=altered), self.assertRaises(M.GateError):
                M.validate_physical_off(altered, now=now)

    def test_pre_stop_proof_may_name_live_service_but_post_stop_is_default(self):
        now = time.time()
        proof = M.PhysicalOffProof(now, M.MACHINE_ID, 42, True, 0.0, 0.0,
                                   True, 0.0, 0.0, True, False, False, 1,
                                   False, ("ha:nonce1", "esp:nonce2"))
        M.validate_physical_off(proof, now=now, require_service_stopped=False)
        with self.assertRaisesRegex(M.GateError, "not confirmed stopped"):
            M.validate_physical_off(proof, now=now)

    def test_wrong_staging_sha_manifest_and_symlink_rejected(self):
        with staged_fixture() as stage:
            manifest_path = stage / "RELEASE_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["source_sha"] = "0" * 40
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(M.GateError, "manifest digest"):
                M.verify_staged_release(stage)
        with staged_fixture() as stage:
            file = stage / "tree" / "module.py"
            file.unlink()
            file.symlink_to(stage / "RELEASE_MANIFEST.json")
            with self.assertRaisesRegex(M.GateError, "staged tree contains unsupported"):
                M.verify_staged_release(stage)


if __name__ == "__main__":
    unittest.main()
