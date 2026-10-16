"""Hardware-inert tests for the standalone D061 kill supervisor foundation."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from tools.acceptance_guard.independent_off import independent_output_off
from tools.acceptance_guard.kill_supervisor import (
    ADOPTION_CHECKS, ChildIdentity, GlobalLock, KillSupervisor, Stage,
    adopted_proof_is_full, verify_child,
)


def report(t, output=False, volts=0, amps=0, protection="NORMAL"):
    return dict(timestamp=t, output=output, voltage=volts, current=amps, protection=protection)


class OffTests(unittest.TestCase):
    def callbacks(self, **overrides):
        now = time.time()
        calls = []
        ticks = [0.0]
        def monotonic():
            return ticks[0]
        def sleep(seconds):
            ticks[0] += seconds
        cb = dict(ha_off_command=lambda: calls.append("ha-off"),
            native_off_command=lambda: calls.append("native-off"),
            ha_readback=lambda: report(now), native_readback=lambda: report(now + .001),
            disarm_lease=lambda: True,
            lease_readback=lambda: dict(timestamp=now + .002, armed=False, generation=7),
            retire_ownership=lambda: True, retire_poller=lambda: True,
            expected_generation=7, clock=lambda: now + .003,
            monotonic=monotonic, sleep=sleep)
        cb.update(overrides)
        return cb, calls

    def test_commands_both_transports_and_accepts_independent_off_readbacks(self):
        cb, calls = self.callbacks()
        proof = independent_output_off(**cb)
        self.assertEqual(calls, ["ha-off", "native-off"])
        self.assertTrue(proof.ha_off and proof.native_off)

    def test_command_ack_without_physical_off_is_not_proof(self):
        cb, _ = self.callbacks(ha_readback=lambda: report(time.time(), True, 12, .2))
        with self.assertRaises(RuntimeError):
            independent_output_off(**cb)

    def test_native_stale_and_equal_source_timestamp_fail(self):
        cb, _ = self.callbacks(native_readback=lambda: report(time.time() - 50))
        with self.assertRaises(RuntimeError):
            independent_output_off(**cb)
        cb, _ = self.callbacks(native_readback=lambda: report(100), ha_readback=lambda: report(100),
                               clock=lambda: 100)
        with self.assertRaises(RuntimeError):
            independent_output_off(**cb)

    def test_armed_or_generation_mismatch_and_retirement_failure_fail(self):
        for lr in (dict(timestamp=time.time(), armed=True, generation=7),
                    dict(timestamp=time.time(), armed=False, generation=8)):
            cb, _ = self.callbacks(lease_readback=lambda lr=lr: lr)
            with self.assertRaises(RuntimeError):
                independent_output_off(**cb)
        cb, _ = self.callbacks(retire_poller=lambda: False)
        with self.assertRaises(RuntimeError):
            independent_output_off(**cb)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage_file = self.root / "stage"
        self.stage_file.write_text("inert test stage")
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.pid = 4242
        proc = self.proc / str(self.pid)
        proc.mkdir()
        self.args = ("/usr/bin/python3", "-c", "pass")
        (proc / "cmdline").write_bytes(b"\0".join(x.encode() for x in self.args) + b"\0")
        # Linux stat field 22 is index 19 after comm/state (field 3 onward).
        (proc / "stat").write_text("4242 (python3) " + " ".join(["S"] + ["0"] * 18 + ["123456"]))
        self.start = 123456
        self.cgroup = "0::/test-stage\n"
        (proc / "cgroup").write_text(self.cgroup)
        self.identity = ChildIdentity(self.pid, self.args, self.start, self.cgroup,
                                      hashlib.sha256(self.stage_file.read_bytes()).hexdigest())
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait()
        self.temp.cleanup()

    def test_identity_mismatch_pid_reuse_and_production_bot_rejected(self):
        verify_child(self.identity, proc_root=self.proc, stage_file=self.stage_file)
        with self.assertRaises(RuntimeError):
            verify_child(ChildIdentity(self.pid, self.args, 4, self.cgroup, self.identity.stage_sha256),
                         proc_root=self.proc, stage_file=self.stage_file)
        (self.proc / str(self.pid) / "cmdline").write_bytes(b"python\0bot.py\0")
        with self.assertRaises(RuntimeError):
            verify_child(self.identity, proc_root=self.proc, stage_file=self.stage_file)

    def test_missing_or_duplicate_pid_does_not_create_acceptance_identity(self):
        with self.assertRaises((FileNotFoundError, RuntimeError)):
            verify_child(ChildIdentity(98765, self.args, self.start, self.cgroup,
                          self.identity.stage_sha256), proc_root=self.proc, stage_file=self.stage_file)
        with self.assertRaises(RuntimeError):
            verify_child(ChildIdentity(os.getpid(), self.args, self.start, self.cgroup,
                          self.identity.stage_sha256), proc_root=self.proc, stage_file=self.stage_file)

    def test_proof_requires_exact_canonical_nineteen_predicates(self):
        full = {name: True for name in ADOPTION_CHECKS}
        self.assertEqual(len(full), 19)
        self.assertFalse(adopted_proof_is_full({'checks': dict(list(full.items())[:-1]), 'failed_predicates': []}))
        self.assertFalse(adopted_proof_is_full({'checks': full | {'extra': True}, 'failed_predicates': []}))
        self.assertFalse(adopted_proof_is_full({'checks': full, 'failed_predicates': ['guard_fresh']}))
        self.assertFalse(adopted_proof_is_full({'checks': full}))
        self.assertTrue(adopted_proof_is_full({'checks': full, 'failed_predicates': []}))

    def test_lock_is_nonblocking_and_never_unlinked(self):
        path = self.root / "lock"
        path.touch(mode=0o600)
        os.chmod(path, 0o600)
        one = GlobalLock(path, euid=lambda: 0, owner_uid=os.getuid())
        one.acquire()
        two = GlobalLock(path, euid=lambda: 0, owner_uid=os.getuid())
        try:
            with self.assertRaises(RuntimeError):
                two.acquire()
        finally:
            one.close()
        self.assertTrue(path.exists())

    def test_lock_rejects_symlink(self):
        target = self.root / "target"
        target.touch(mode=0o600)
        path = self.root / "link"
        path.symlink_to(target)
        with self.assertRaises(RuntimeError):
            GlobalLock(path, euid=lambda: 0, owner_uid=os.getuid()).acquire()

    def _supervisor(self, **kw):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.children.append(child)
        proc_identity = __import__("tools.acceptance_guard.kill_supervisor", fromlist=["_proc_identity"])._proc_identity
        # /proc/<pid>/cmdline is legitimately empty until execve finishes.
        # Wait for the test child to become identifiable, never skip its attestation.
        deadline = time.monotonic() + 2.0
        while True:
            try:
                args, start, cgroup = proc_identity(child.pid)
                break
            except RuntimeError as exc:
                if str(exc) != "child cmdline unavailable" or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)
        identity = ChildIdentity(child.pid, args, start, cgroup, self.identity.stage_sha256)
        events = kw.pop("events", [])
        now = time.time()
        ticks = [10.0]
        def monotonic():
            ticks[0] += .01
            return ticks[0]
        def sleep(seconds):
            ticks[0] += seconds
        def kill(pid, sig):
            events.append("kill")
            os.kill(pid, sig)
        native_readback = kw.pop("native_readback", lambda: report(now + .001))
        return KillSupervisor(lock=kw.pop("lock", Mock(acquire=lambda: None, close=lambda: None)),
            child=identity, stage_file=self.stage_file,
            proof_provider=kw.pop("proof_provider", lambda: {'checks': {name: True for name in ADOPTION_CHECKS}, 'failed_predicates': []}),
            ha_off_command=lambda: events.append("ha-off"), native_off_command=lambda: events.append("native-off"),
            ha_readback=lambda: report(now), native_readback=native_readback,
            disarm_lease=lambda: True, lease_readback=lambda: dict(timestamp=now + .002, armed=False, generation=7),
            retire_ownership=lambda: True, retire_poller=lambda: True,
            restore_production=kw.pop("restore_production", lambda: events.append("restore") or True),
            expected_generation=7, kill=kw.pop("kill", kill),
            clock=lambda: now + .003, monotonic=monotonic, sleep=sleep,
            **kw)

    def test_kill_flow_orders_kill_off_retire_then_restore(self):
        events = []
        sup = self._supervisor(events=events)
        self.assertEqual(sup.run(), "PASS")
        self.assertEqual(sup.stage, Stage.RESTORE_ALLOWED)
        self.assertEqual(events[0], "kill")
        self.assertEqual(events[-1], "restore")

    def test_empty_cmdline_live_pid_does_not_count_as_dead(self):
        # An unreadable/empty cmdline is not proof of SIGKILL: the matching
        # PID must either disappear or become a verified zombie.
        sup = KillSupervisor.__new__(KillSupervisor)
        sup.child = self.identity
        elapsed = [0.0]
        sup.monotonic = lambda: elapsed[0]
        sup.sleep = lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
        live_stat = "4242 (python3) " + " ".join(["R"] + ["0"] * 18 + [str(self.start)])
        with patch("tools.acceptance_guard.kill_supervisor._proc_identity",
                   side_effect=RuntimeError("child cmdline unavailable")):
            with patch("pathlib.Path.read_text", return_value=live_stat):
                with self.assertRaisesRegex(TimeoutError, "did not exit"):
                    sup._wait_child_death(0.12)
        self.assertGreaterEqual(elapsed[0], 0.12)

    def test_empty_cmdline_zombie_same_pid_is_confirmed_dead(self):
        sup = KillSupervisor.__new__(KillSupervisor)
        sup.child = self.identity
        sup.monotonic = lambda: 0.0
        sup.sleep = lambda _: self.fail("zombie should not require another poll")
        zombie = "4242 (python3) " + " ".join(["Z"] + ["0"] * 18 + [str(self.start)])
        with patch("tools.acceptance_guard.kill_supervisor._proc_identity",
                   side_effect=RuntimeError("child cmdline unavailable")):
            with patch("pathlib.Path.read_text", return_value=zombie):
                self.assertIsNone(sup._wait_child_death(1.0))

    def test_empty_cmdline_reused_pid_stays_fail_closed(self):
        sup = KillSupervisor.__new__(KillSupervisor)
        sup.child = self.identity
        sup.monotonic = lambda: 0.0
        sup.sleep = lambda _: self.fail("reused PID must not be retried")
        reused = "4242 (python3) " + " ".join(["Z"] + ["0"] * 18 + [str(self.start + 1)])
        with patch("tools.acceptance_guard.kill_supervisor._proc_identity",
                   side_effect=RuntimeError("child cmdline unavailable")):
            with patch("pathlib.Path.read_text", return_value=reused):
                with self.assertRaisesRegex(RuntimeError, "PID was reused"):
                    sup._wait_child_death(1.0)

    def test_no_off_timeout_restoration_guarded(self):
        events = []
        sup = self._supervisor(events=events, native_readback=lambda: report(time.time(), True, 12, .2))
        with self.assertRaises(RuntimeError):
            sup.run()
        self.assertEqual(sup.stage, Stage.FAIL_CLOSED)
        self.assertNotIn("restore", events)

    def test_incomplete_adoption_child_death_or_cancellation_never_restores(self):
        for proof in ({"checks": {"only": True}},):
            events = []
            sup = self._supervisor(events=events, proof_provider=lambda: proof)
            with self.assertRaises(RuntimeError):
                sup.run()
            self.assertNotIn("kill", events)
            self.assertNotIn("restore", events)
        events = []
        sup = self._supervisor(events=events, kill=lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            sup.run()
        self.assertEqual(sup.stage, Stage.FAIL_CLOSED)
        self.assertNotIn("restore", events)


if __name__ == "__main__":
    unittest.main()
