import fcntl
import os
from pathlib import Path
import tempfile
import unittest

from tools.acceptance_guard.fixture_supervisor import (
    Disposition, FixtureSupervisor, LeaseReadback, Readback, off_then_disarm,
    verify_independent_off,
)


class SupervisorFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lock_path = self.root / "acceptance.lock"
        self.lock_path.touch(mode=0o600)
        self.script = self.root / "synthetic_child.py"
        self.script.write_text(
            "import fcntl, os, stat, sys, time\n"
            "path = sys.argv[1]\n"
            "st = os.stat(path)\n"
            "assert stat.S_ISREG(st.st_mode)\n"
            "assert (st.st_dev, st.st_ino) == (int(sys.argv[2]), int(sys.argv[3]))\n"
            "# Child can open its OWN descriptor, but cannot unlock parent.\n"
            "own = os.open(path, os.O_RDONLY)\n"
            "fcntl.flock(own, fcntl.LOCK_UN)\n"
            "os.close(own)\n"
            "open(sys.argv[4], 'w').write('ready')\n"
            "time.sleep(60)\n")
        self.supervisor = FixtureSupervisor(self.lock_path)
        self.supervisor.acquire()

    def tearDown(self):
        if self.supervisor.child is not None and self.supervisor.child.poll() is None:
            self.supervisor.child.kill()
            self.supervisor.child.wait(timeout=2)
        self.supervisor.close()
        self.temp.cleanup()

    def test_synthetic_sigkill_keeps_parent_lock_and_blocks_duplicate_acceptance(self):
        child = self.supervisor.start_synthetic_child(self.script)
        self.assertGreater(child.pid, 1)
        # Synthetic child attempted LOCK_UN on its independent descriptor;
        # the supervisor must still own its separate open file description.
        self.supervisor.assert_lock_held()
        with self.assertRaisesRegex(RuntimeError, "duplicate acceptance"):
            self.supervisor.start_synthetic_child(self.script)
        contender = os.open(self.lock_path, os.O_RDWR)
        try:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(contender)
        self.supervisor.kill_synthetic_child(self.script)
        self.assertEqual(self.supervisor.child.returncode, -9)
        self.supervisor.assert_lock_held()

    def test_source_identity_change_refuses_synthetic_kill(self):
        self.supervisor.start_synthetic_child(self.script)
        self.script.write_text("# changed fixture\n")
        with self.assertRaisesRegex(RuntimeError, "source SHA"):
            self.supervisor.kill_synthetic_child(self.script)

    def test_stale_handshake_marker_cannot_claim_child_readiness(self):
        (self.root / "synthetic_child.ready").write_text("stale")
        with self.assertRaisesRegex(RuntimeError, "stale fixture ready"):
            self.supervisor.start_synthetic_child(self.script)
        self.assertIsNone(self.supervisor.child)
        self.supervisor.assert_lock_held()

    def test_production_script_name_is_rejected(self):
        bot = self.root / "bot.py"
        bot.write_text("pass\n")
        with self.assertRaisesRegex(RuntimeError, "only launches synthetic"):
            self.supervisor.start_synthetic_child(bot)


class IndependentOffFixtureTests(unittest.TestCase):
    def reports(self, *, output=False, age=0.0, shared=False):
        first = Readback("ha-fixture", "ha-1", 100.0 - age, output, 0.0, 0.0, "NORMAL")
        second = Readback("ha-fixture" if shared else "native-fixture", "ha-2" if shared else "native-1",
                          100.0 - age, output, 0.0, 0.0, "NORMAL")
        return first, second

    def test_unconfirmed_off_is_hold_and_does_not_disarm(self):
        first, second = self.reports(output=True)
        calls = []
        result = off_then_disarm(first=first, second=second,
                                 disarm=lambda _cutoff: calls.append("disarm") or True,
                                 lease_readback=lambda _cutoff: None, now=lambda: 100.0, deadline=45.0)
        self.assertEqual(result, Disposition.HOLD)
        self.assertEqual(calls, [])

    def test_stale_or_same_source_reports_cannot_prove_off(self):
        fresh, _ = self.reports()
        _, shared = self.reports(shared=True)
        stale, native = self.reports(age=3.01)
        self.assertFalse(verify_independent_off(fresh, shared, now=100.0))
        self.assertFalse(verify_independent_off(stale, native, now=100.0))

    def test_disarm_requires_independent_fresh_disarmed_lease_readback(self):
        first, second = self.reports()
        calls = []
        result = off_then_disarm(
            first=first, second=second, disarm=lambda _cutoff: calls.append("disarm") or True,
            lease_readback=lambda _cutoff: LeaseReadback("edge-fixture", "lease-1", 100.0, False),
            now=lambda: 100.0, deadline=45.0)
        self.assertEqual(result, Disposition.LEASE_DISARMED)
        self.assertEqual(calls, ["disarm"])

        calls.clear()
        result = off_then_disarm(
            first=first, second=second, disarm=lambda _cutoff: calls.append("disarm") or True,
            lease_readback=lambda _cutoff: LeaseReadback("ha-fixture", "lease-1", 100.0, False),
            now=lambda: 100.0, deadline=45.0)
        self.assertEqual(result, Disposition.HOLD)
        self.assertEqual(calls, ["disarm"])

    def test_deadline_cannot_exceed_45_seconds(self):
        first, second = self.reports()
        with self.assertRaisesRegex(ValueError, "45"):
            off_then_disarm(first=first, second=second, disarm=lambda _cutoff: True,
                            lease_readback=lambda _cutoff: None, now=lambda: 100.0, deadline=45.1)

    def test_overdue_disarm_ack_stays_hold_and_never_reads_lease(self):
        first, second = self.reports()
        clock = [100.0]
        lease_calls = []
        def slow_disarm(cutoff):
            self.assertEqual(cutoff, 145.0)
            clock[0] = 145.0
            return True
        result = off_then_disarm(first=first, second=second, disarm=slow_disarm,
                                 lease_readback=lambda _cutoff: lease_calls.append(True),
                                 now=lambda: clock[0], deadline=45.0)
        self.assertEqual(result, Disposition.HOLD)
        self.assertEqual(lease_calls, [])


if __name__ == "__main__":
    unittest.main()
