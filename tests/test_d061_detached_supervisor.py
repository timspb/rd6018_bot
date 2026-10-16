"""Hardware-inert contracts for detached parent/child integration."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tools.acceptance_guard.bounded import run_bounded
from tools.acceptance_guard.detached import (
    LOCK_FD_ENV, PROOF_KEYS, verify_live_adoption_proof,
)
from tools.acceptance_guard.kill_supervisor import ADOPTION_CHECKS, ChildIdentity
from tools.acceptance_guard.stop_off import main as stop_off_main


class DetachedProofTests(unittest.TestCase):
    def setUp(self):
        self.identity = ChildIdentity(4321, ("/usr/bin/python3", "acceptance_child.py"),
            1234, "0::/test/acceptance\n", "a" * 64)

    def proof(self, **changes):
        t = 20.0
        value = {"schema": "D061-adoption-proof/1", "epoch": 2,
            "observed_monotonic": t,
            "child": {"pid": self.identity.pid, "start_time": self.identity.start_time,
                "cmdline": list(self.identity.cmdline), "cgroup": self.identity.cgroup,
                "stage_sha256": self.identity.stage_sha256},
            "checks": {name: {"ok": True, "observed_monotonic": t}
                       for name in ADOPTION_CHECKS}}
        value.update(changes)
        return value

    def test_exact_canonical_source_keyset_fresh_and_monotonic(self):
        proof = self.proof()
        self.assertEqual(set(proof), PROOF_KEYS)
        self.assertEqual(len(proof["checks"]), 19)
        self.assertEqual(verify_live_adoption_proof(proof, self.identity,
            previous_epoch=1, now_monotonic=21), 2)
        for bad in (
            self.proof(checks={"19": True}),
            self.proof(checks=dict(self.proof()["checks"], forged={"ok": True, "observed_monotonic": 20})),
            self.proof(child={"pid": 99}),
            self.proof(epoch=1), self.proof(epoch=True),
            self.proof(observed_monotonic=17),
        ):
            with self.assertRaises(RuntimeError):
                verify_live_adoption_proof(bad, self.identity, previous_epoch=1, now_monotonic=21)
        stale_check = self.proof()
        stale_check["checks"][next(iter(ADOPTION_CHECKS))]["observed_monotonic"] = 10
        with self.assertRaises(RuntimeError):
            verify_live_adoption_proof(stale_check, self.identity, previous_epoch=1, now_monotonic=21)

    def test_no_stop_restoration_or_off_without_reviewed_adapter(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stop_off_main(), 78)


class BoundedCallbackTests(unittest.TestCase):
    def test_infinite_callback_is_killed_by_os_deadline(self):
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            run_bounded(lambda: time.sleep(30), .15)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_callback_value_and_failure_propagate(self):
        self.assertEqual(run_bounded(lambda: 7, 1), 7)
        with self.assertRaisesRegex(RuntimeError, "callback failed"):
            run_bounded(lambda: (_ for _ in ()).throw(ValueError("inert")), 1)

    def test_worker_does_not_inherit_parent_lock_or_other_descriptors(self):
        fd = os.open(os.devnull, os.O_RDONLY)
        try:
            def inspect():
                try:
                    os.fstat(fd)
                    return False
                except OSError:
                    return True
            self.assertTrue(run_bounded(inspect, 1))
            os.fstat(fd)  # worker cleanup did not affect parent ownership
        finally:
            os.close(fd)


class SystemdTemplateTests(unittest.TestCase):
    def test_opt_in_watchdog_runtime_and_stop_hook_are_present(self):
        unit = (Path(__file__).parents[1] / "tools/acceptance_guard/rd6018-d061-detached@.service").read_text()
        self.assertIn("WatchdogSec=10s", unit)
        self.assertIn("RuntimeMaxSec=90s", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertIn("ExecStopPost=/opt/services/rd6018-bot/venv/bin/python -m tools.acceptance_guard.stop_off", unit)
        self.assertIn("KillMode=process", unit)


@unittest.skipUnless(os.geteuid() == 0, "root-owned 0600 production lock contract")
class ParentLockHandoffTests(unittest.TestCase):
    def test_inherited_descriptor_survives_child_exit_and_blocks_unrelated_flock(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "lock"
            fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
            os.chmod(lock, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                before = os.fstat(fd)
                env = dict(os.environ, **{LOCK_FD_ENV: str(fd), "LOCK_PATH": str(lock)})
                code = ("import os; from pathlib import Path; "
                    "from tools.acceptance_guard.detached import inherited_parent_gate; "
                    "g=inherited_parent_gate(lock_path=Path(os.environ['LOCK_PATH'])); "
                    "with_dummy=0; "
                    "exec('with g(): pass')")
                child = subprocess.run([sys.executable, "-c", code], env=env,
                    pass_fds=(fd,), close_fds=True, check=False)
                self.assertEqual(child.returncode, 0)
                after = os.fstat(fd)
                self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
                contender = os.open(lock, os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(contender)
            finally:
                os.close(fd)

    def test_wrong_inode_or_missing_fd_is_denied(self):
        from tools.acceptance_guard.detached import inherited_parent_gate
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            path.touch(mode=0o600)
            os.chmod(path, 0o600)
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
                inherited_parent_gate(lock_path=path)


if __name__ == "__main__":
    unittest.main()
