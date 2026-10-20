import importlib.util
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "node104_atomic_deploy.py"
SPEC = importlib.util.spec_from_file_location("node104_atomic_deploy", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Node104TransactionTests(unittest.TestCase):
    def test_no_production_activation_or_rollback_cli(self):
        self.assertFalse(hasattr(MODULE, "activate"))
        self.assertFalse(hasattr(MODULE, "rollback"))
        with self.assertRaises(SystemExit):
            MODULE.main(["activate", "--sha", "deadbeef"])

    def test_preflight_blocks_actual_ordinary_topology_and_mismatched_firmware(self):
        evidence = {
            "node": "node104", "service": "rd6018-bot", "exec_start": MODULE.EXPECTED_EXEC_START,
            "protect_system": "strict", "filesystem_topology": "ordinary_directory",
            "captured_at_epoch": 1000, "service_stopped": True, "output_state": 0,
            "measured_voltage_v": 0, "measured_current_a": 0, "edge_lease_contained": True,
            "installed_firmware": MODULE.EXPECTED_INSTALLED_FIRMWARE,
            "firmware_contract_matched": False,
            "independent_sources": ["systemd", "physical_readback", "edge_lease", "firmware_identity"],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.json"
            path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(RuntimeError, "matched candidate edge contract"):
                MODULE.preflight(path, now=1001)

    def test_preflight_blocks_stale_or_nonzero_independent_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.json"
            path.write_text(json.dumps({"node": "node104", "captured_at_epoch": 1,
                                        "measured_voltage_v": 13.57, "measured_current_a": .1}))
            with self.assertRaisesRegex(RuntimeError, "stale"):
                MODULE.preflight(path, now=MODULE.MAX_PREFLIGHT_AGE_SECONDS + 2)

    def test_safe_relative_rejects_traversal_absolute_and_windows_paths(self):
        for name in ("../escape", "/absolute", "C:\\escape", "a/../../escape"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                MODULE._safe_relative(name)

    def test_manifest_verification_rejects_mode_mismatch(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root / "artifact.py"
            payload.write_bytes(b"SOURCE = True\n")
            payload.chmod(0o644)
            manifest = {
                "node": MODULE.EXPECTED_NODE,
                "service": MODULE.EXPECTED_SERVICE,
                "files": [{"path": "artifact.py", "mode": 0o644,
                           "size": payload.stat().st_size,
                           "sha256": hashlib.sha256(payload.read_bytes()).hexdigest()}],
            }
            MODULE.verify_manifest(root, manifest)
            payload.chmod(0o600)
            with self.assertRaisesRegex(RuntimeError, "manifest mismatch"):
                MODULE.verify_manifest(root, manifest)

    @unittest.skipUnless(
        shutil.which("git") is not None and (Path(__file__).parents[1] / ".git").exists(),
        "Git stage test requires VCS checkout (runs in CI; source.tar has no .git)",
    )
    def test_stage_is_exact_sha_and_digest_verified(self):
        repo = Path(__file__).parents[1]
        sha = MODULE.run("git", "-C", str(repo), "rev-parse", "HEAD")
        with tempfile.TemporaryDirectory() as temp:
            release = MODULE.stage(repo, sha, Path(temp) / "staging")
            manifest = json.loads((release / MODULE.MANIFEST_NAME).read_text())
            marker = json.loads((release / MODULE.STAGED_MARKER).read_text())
            self.assertEqual(sha, manifest["source_sha"])
            self.assertTrue(marker["tree_verified"])
            self.assertEqual(MODULE.sha256(release / MODULE.MANIFEST_NAME), marker["manifest_sha256"])
            MODULE.verify_manifest(release / "tree", manifest)

    def test_simulated_swap_is_atomic_and_leaves_durable_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.app.mkdir(parents=True)
            (layout.app / "version").write_text("old")
            staged = Path(temp) / "candidate"
            staged.mkdir()
            (staged / "version").write_text("new")
            self.assertEqual("COMMITTED", MODULE.simulate_transaction(layout, staged, "abc123"))
            self.assertEqual("new", (layout.app / "version").read_text())
            self.assertEqual("old", (layout.backups / "backup-abc123" / "version").read_text())
            self.assertEqual("COMMITTED", json.loads(layout.journal.read_text())["state"])

    def test_crash_after_each_swap_point_recovers_idempotently(self):
        for crash in ("BACKUP_DURABLE", "SWAP_OLD_RENAMED", "SWAP_NEW_RENAMED",
                      "SWAP_OLD_RENAMED_BEFORE_JOURNAL", "SWAP_NEW_RENAMED_BEFORE_JOURNAL"):
            with self.subTest(crash=crash), tempfile.TemporaryDirectory() as temp:
                layout = MODULE.SimulationLayout(Path(temp))
                layout.app.mkdir(parents=True)
                (layout.app / "version").write_text("old")
                staged = Path(temp) / "candidate"
                staged.mkdir()
                (staged / "version").write_text("new")
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    MODULE.simulate_transaction(layout, staged, "crash", crash_after=crash)
                self.assertEqual("ROLLED_BACK", MODULE.recover(layout))
                self.assertEqual("ROLLED_BACK", MODULE.recover(layout))
                self.assertEqual("old", (layout.app / "version").read_text())

    def test_recovery_rejects_journal_path_traversal_and_corrupt_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.app.mkdir(parents=True)
            (layout.app / "version").write_text("old")
            staged = Path(temp) / "candidate"
            staged.mkdir()
            (staged / "version").write_text("new")
            with self.assertRaises(RuntimeError):
                MODULE.simulate_transaction(layout, staged, "bad", crash_after="BACKUP_DURABLE")
            record = json.loads(layout.journal.read_text())
            record["backup"] = str(Path(temp).parent / "escape")
            layout.journal.write_text(json.dumps(record))
            with self.assertRaisesRegex(RuntimeError, "escapes"):
                MODULE.recover(layout)

            record["backup"] = str(layout.backups / "backup-bad")
            (layout.backups / "backup-bad" / "version").write_text("tampered")
            layout.journal.write_text(json.dumps(record))
            with self.assertRaisesRegex(RuntimeError, "corrupted"):
                MODULE.recover(layout)

    def test_recovery_requires_initialized_root(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.journal.write_text("not-json")
            with self.assertRaisesRegex(RuntimeError, "initialized"):
                MODULE.recover(layout)

    def test_recovery_rejects_impossible_rename_state(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.root.mkdir(exist_ok=True)
            MODULE._write_simulation_marker(layout)
            layout.backups.mkdir()
            backup = layout.backups / "backup-x"
            backup.mkdir()
            (backup / "version").write_text("old")
            record = {"schema": 2, "node": "node104", "service": "rd6018-bot",
                      "state": "BACKUP_DURABLE", "source_sha": "x",
                      "backup": str(backup), "backup_manifest": MODULE._tree_manifest(backup)}
            layout.journal.write_text(json.dumps(record))
            with self.assertRaisesRegex(RuntimeError, "impossible"):
                MODULE.recover(layout)

    def test_same_filesystem_and_root_containment_are_preflighted(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.app.mkdir(parents=True)
            (layout.app / "version").write_text("old")
            staged = Path(outside) / "candidate"
            staged.mkdir()
            with self.assertRaisesRegex(RuntimeError, "contained"):
                MODULE.simulate_transaction(layout, staged, "outside")

    def test_recovery_lock_is_exclusive_when_held(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.root.mkdir(exist_ok=True)
            MODULE._write_simulation_marker(layout)
            held = MODULE._acquire_lock(layout)
            try:
                with self.assertRaisesRegex(RuntimeError, "owns the journal lock"):
                    MODULE._acquire_lock(layout, allow_stale_file=True)
            finally:
                held.close(remove=True)

    def test_concurrent_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            layout = MODULE.SimulationLayout(Path(temp))
            layout.lock.write_text("other")
            with self.assertRaisesRegex(RuntimeError, "owns the journal lock"):
                MODULE.simulate_transaction(layout, Path(temp), "x")


if __name__ == "__main__":
    unittest.main()
