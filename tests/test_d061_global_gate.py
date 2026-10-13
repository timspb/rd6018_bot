"""Hardware-free cross-window arbitration for the node104 physical acceptance lock."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.acceptance_guard import pairing


class D061GlobalGateTests(unittest.TestCase):
    def setUp(self):
        # Unit tests run under an unprivileged developer account. Model only
        # node104's root identity; retain the real kernel inode and flock.
        original_fstat = os.fstat

        def fake_root_fstat(fd):
            values = list(original_fstat(fd))
            values[4] = 0  # st_uid
            return os.stat_result(values)

        root = patch.object(pairing.os, 'geteuid', return_value=0)
        fstat = patch.object(pairing.os, 'fstat', side_effect=fake_root_fstat)
        root.start()
        fstat.start()
        self.addCleanup(fstat.stop)
        self.addCleanup(root.stop)
    def test_one_node_lock_rejects_a_second_window_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "physical.lock"
            with patch.object(pairing, "NODE104_ACCEPTANCE_LOCK", lock), patch.object(
                pairing, "_noncooperating_acceptance_pids", return_value=[]
            ):
                with pairing.node104_acceptance_gate():
                    with self.assertRaisesRegex(RuntimeError, "another node104 acceptance"):
                        with pairing.node104_acceptance_gate():
                            pass
                with pairing.node104_acceptance_gate():
                    pass
            self.assertTrue(lock.is_file())
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)

    def test_old_python_c_acceptance_owner_blocks_new_window(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(pairing, "NODE104_ACCEPTANCE_LOCK", Path(temp)/"physical.lock"), patch.object(
                pairing, "_noncooperating_acceptance_pids", return_value=[51997]
            ):
                with self.assertRaisesRegex(RuntimeError, "legacy acceptance"):
                    with pairing.node104_acceptance_gate():
                        pass

    def test_unsafe_preexisting_lock_file_permissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "physical.lock"
            lock.touch()
            lock.chmod(0o644)
            with patch.object(pairing, "NODE104_ACCEPTANCE_LOCK", lock):
                with self.assertRaisesRegex(RuntimeError, "untrusted global D061 lock"):
                    with pairing.node104_acceptance_gate():
                        pass

    def test_symlink_lock_is_rejected(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unsupported")
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            real.touch(mode=0o600)
            alias = Path(temp) / "physical.lock"
            alias.symlink_to(real)
            with patch.object(pairing, "NODE104_ACCEPTANCE_LOCK", alias):
                with self.assertRaises(OSError):
                    with pairing.node104_acceptance_gate():
                        pass


class D061LegacyScannerTests(unittest.TestCase):
    def test_finds_unmanaged_python_c_owner_even_without_bot_py(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp)
            old = proc / "51997"
            old.mkdir()
            (old / "comm").write_text("python\\n")
            (old / "cmdline").write_bytes(
                b"python\\0-B\\0-c\\0from tools.acceptance_guard.takeover "
                b"import run_node104; asyncio.run(run_node104("
                b"Path('/tmp/rd6018-d061-takeover-legacy')))\\0")
            self.assertEqual(pairing._noncooperating_acceptance_pids(proc), [51997])
            (old / "cmdline").write_bytes(b"python\\0ordinary-script.py\\0")
            self.assertEqual(pairing._noncooperating_acceptance_pids(proc), [])


class D061EntrypointTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_node104_entry_requires_shared_gate_before_stage(self):
        from tools.acceptance_guard.takeover import run_node104
        with patch.object(pairing, "node104_acceptance_gate",
                          side_effect=RuntimeError("shared gate denied")):
            with self.assertRaisesRegex(RuntimeError, "shared gate denied"):
                await run_node104("/tmp/nonexistent-physical-acceptance")


if __name__ == "__main__":
    unittest.main()
