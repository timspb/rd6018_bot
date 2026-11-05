import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import node104_d090_transaction as d090
from node104_d090_transaction import SystemdService


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class D127StartupWaitTests(unittest.TestCase):
    def service(self):
        svc = object.__new__(SystemdService)
        svc.pinned = type('Pin', (), {'source_sha': 'a', 'old_source_sha': 'b'})()
        return svc

    def test_delayed_polling_after_41_seconds_is_accepted(self):
        svc, clock = self.service(), FakeClock()
        def ready(_sha, expected_pid=None):
            return clock.now >= 42
        with patch.object(SystemdService, '_stable_process', side_effect=ready), \
             patch.object(SystemdService, 'active', return_value=True), \
             patch.object(SystemdService, 'main_pid', return_value=21), \
             patch.object(d090.time, 'monotonic', side_effect=clock.monotonic), \
             patch.object(d090.time, 'sleep', side_effect=clock.sleep):
            self.assertTrue(svc.stable('a'))
        self.assertGreaterEqual(clock.now, 42)

    def test_timeout_is_bounded_at_120_seconds(self):
        svc, clock = self.service(), FakeClock()
        with patch.object(SystemdService, '_stable_process', return_value=False), \
             patch.object(SystemdService, 'active', return_value=True), \
             patch.object(SystemdService, 'main_pid', return_value=21), \
             patch.object(d090.time, 'monotonic', side_effect=clock.monotonic), \
             patch.object(d090.time, 'sleep', side_effect=clock.sleep):
            self.assertFalse(svc.stable('a'))
        self.assertEqual(clock.now, 120)

    def test_service_exit_fails_closed_without_wait(self):
        svc, clock = self.service(), FakeClock()
        with patch.object(SystemdService, 'active', return_value=False), \
             patch.object(d090.time, 'monotonic', side_effect=clock.monotonic), \
             patch.object(d090.time, 'sleep', side_effect=clock.sleep):
            self.assertFalse(svc.stable('a'))
        self.assertEqual(clock.now, 0)

    def test_wrong_pid_is_rejected(self):
        svc = self.service()
        with patch.object(SystemdService, 'active', return_value=True), \
             patch.object(SystemdService, 'main_pid', return_value=22):
            self.assertFalse(svc._stable_process('a', expected_pid=21))

    def test_duplicate_bot_owner_is_rejected(self):
        svc = self.service()
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            script = str(Path(d090.release.ROOT) / 'app' / 'bot.py').encode()
            for pid in (21, 22):
                entry = proc / str(pid)
                entry.mkdir()
                (entry / 'cmdline').write_bytes(b'/usr/bin/python\0' + script + b'\0')
            original_iterdir = Path.iterdir
            def iterdir(path):
                return proc.iterdir() if path == Path('/proc') else original_iterdir(path)
            def run(*args):
                if 'NRestarts' in args:
                    return '0'
                if 'ActiveEnterTimestamp' in args:
                    return 'Thu 2026-11-06 00:00:00 UTC'
                if args[0] == 'journalctl':
                    return 'Run polling for bot'
                raise AssertionError(args)
            with patch.object(SystemdService, 'active', return_value=True), \
                 patch.object(SystemdService, 'main_pid', return_value=21), \
                 patch.object(SystemdService, '_run', side_effect=run), \
                 patch.object(Path, 'iterdir', iterdir):
                self.assertFalse(svc._stable_process('a'))

    def test_start_epoch_log_read_detects_fault_and_requires_poll(self):
        svc = self.service()
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            entry = proc / '21'; entry.mkdir()
            script = str(Path(d090.release.ROOT) / 'app' / 'bot.py').encode()
            (entry / 'cmdline').write_bytes(b'/usr/bin/python\0' + script + b'\0')
            original_iterdir = Path.iterdir
            def iterdir(path):
                return proc.iterdir() if path == Path('/proc') else original_iterdir(path)
            commands = []
            def run(*args):
                commands.append(args)
                if 'NRestarts' in args: return '0'
                if 'ActiveEnterTimestamp' in args: return 'Thu 2026-11-06 00:00:00 UTC'
                if args[0] == 'journalctl': return 'Traceback (most recent call last)'
                raise AssertionError(args)
            with patch.object(SystemdService, 'active', return_value=True), \
                 patch.object(SystemdService, 'main_pid', return_value=21), \
                 patch.object(SystemdService, '_run', side_effect=run), \
                 patch.object(Path, 'iterdir', iterdir):
                self.assertFalse(svc._stable_process('a'))
            journal = next(args for args in commands if args[0] == 'journalctl')
            self.assertIn('Thu 2026-11-06 00:00:00 UTC', journal)


if __name__ == '__main__':
    unittest.main()
