from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

SPEC = importlib.util.spec_from_file_location("d090", Path(__file__).parents[1] / "tools/node104_d090_release.py")
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)
STAGING = Path("/tmp/rd6018-d089-20261017-staging/release-d29db790bf7140932bc005bddf6bd5988041bfc0-ukm77bsk")


class ReleaseVerification(unittest.TestCase):
    def test_exact_supplied_staging_passes_integrity(self):
        manifest = M.verify_staged_release(STAGING)
        self.assertEqual(manifest["source_sha"], M.SOURCE_SHA)
        report = M.preflight_report(STAGING)
        self.assertEqual(report["decision"], "PREPARE_ONLY_PASS")
        self.assertFalse(report["activation_authorized"])
        self.assertTrue(report["blockers"])

    def test_archive_corruption_and_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            clone = Path(temp) / "release"
            shutil.copytree(STAGING, clone)
            with (clone / "source.tar").open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(M.GateError, "archive"):
                M.verify_staged_release(clone)

    def test_physical_gate_requires_fresh_two_source_off_zero_and_stopped(self):
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
            replace(proof, ha102_current_a=0.2),
            replace(proof, edge_lease_armed=True),
            replace(proof, active_session=True),
            replace(proof, source_nonces=("same", "same")),
        ):
            with self.subTest(proof=altered), self.assertRaises(M.GateError):
                M.validate_physical_off(altered, now=now)

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
        for altered in (replace(proof, ha102_output_off=1),
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
        with tempfile.TemporaryDirectory() as temp:
            clone = Path(temp) / "release"
            shutil.copytree(STAGING, clone)
            manifest_path = clone / "RELEASE_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["source_sha"] = "0" * 40
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(M.GateError, "manifest digest"):
                M.verify_staged_release(clone)


if __name__ == "__main__":
    unittest.main()
