"""D108: source-only fake-root lifecycle, no systemd or hardware writes."""
from pathlib import Path
import os
import socket
import stat
import tempfile
import unittest

from tools.node104_d108_socket_lease import (
    DROPIN_BYTES, TemporarySocketLease, SocketLeaseError,
)


class TemporarySocketLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="d108-socket-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dropin_dir = self.root / "systemd" / "rd6018.service.d"
        self.dropin_dir.parent.mkdir()
        self.socket_path = self.root / "run" / "physical.sock"
        self.socket_path.parent.mkdir()
        self.pid = 0
        self.reloads = 0
        def reload():
            self.reloads += 1
        self.lease = TemporarySocketLease(
            dropin_dir=self.dropin_dir, socket=self.socket_path,
            main_pid=lambda: self.pid, daemon_reload=reload, offline=True)

    def test_exact_dropin_install_and_idempotent_cleanup(self):
        self.lease.install()
        self.assertEqual(DROPIN_BYTES, self.lease.dropin.read_bytes())
        self.assertEqual(0o600, stat.S_IMODE(self.lease.dropin.stat().st_mode))
        self.assertEqual(1, self.reloads)
        self.lease.cleanup()
        self.lease.cleanup()
        self.assertFalse(self.lease.dropin.exists())
        self.assertEqual(3, self.reloads)

    def test_live_service_or_unowned_dropins_fail_closed(self):
        self.pid = 888
        with self.assertRaises(SocketLeaseError):
            self.lease.install()
        self.assertFalse(self.dropin_dir.exists())
        self.pid = 0
        self.dropin_dir.mkdir()
        (self.dropin_dir / "operator-override.conf").write_text("do not touch")
        with self.assertRaises(SocketLeaseError):
            self.lease.install()

    def test_foreign_socket_or_symlink_never_unlinked(self):
        self.socket_path.write_text("not a socket")
        with self.assertRaises(SocketLeaseError):
            self.lease.install()
        self.assertTrue(self.socket_path.exists())
        self.socket_path.unlink()
        self.lease.install()
        other = self.root / "outside"
        other.write_text("keep")
        self.socket_path.symlink_to(other)
        with self.assertRaises(SocketLeaseError):
            self.lease.cleanup()
        self.assertEqual("keep", other.read_text())
        self.assertTrue(self.lease.dropin.exists())

    def test_exact_permissions_and_content_mandatory(self):
        self.lease.install()
        self.lease.dropin.write_text("unknown")
        with self.assertRaises(SocketLeaseError):
            self.lease.cleanup()
        self.lease.dropin.write_bytes(DROPIN_BYTES)
        self.lease.dropin.chmod(0o644)
        with self.assertRaises(SocketLeaseError):
            self.lease.cleanup()
        self.lease.dropin.chmod(0o600)
        self.lease.cleanup()
        self.assertFalse(self.lease.dropin.exists())

    def test_unexpected_override_after_install_blocks_old_service_restart(self):
        self.lease.install()
        foreign = self.dropin_dir / "operator-added.conf"
        foreign.write_text("never remove this file")
        with self.assertRaisesRegex(SocketLeaseError, "unreviewed systemd override"):
            self.lease.cleanup()
        self.assertTrue(foreign.exists())
        self.assertTrue(self.lease.dropin.exists())
        foreign.unlink()
        self.lease.cleanup()
        self.assertFalse(self.lease.dropin.exists())

    def test_stale_root_socket_removable_only_when_service_stopped(self):
        self.lease.install()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        self.pid = 42
        with self.assertRaises(SocketLeaseError):
            self.lease.cleanup()
        self.pid = 0
        self.lease.cleanup()
        self.assertFalse(self.socket_path.exists())

    def test_crash_after_dropin_deletion_retries_daemon_reload(self):
        self.lease.install()
        attempts = 0
        def flaky_reload():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("simulated daemon-reload crash")
        self.lease.daemon_reload = flaky_reload
        with self.assertRaisesRegex(RuntimeError, "daemon-reload crash"):
            self.lease.cleanup()
        self.assertFalse(self.lease.dropin.exists())
        self.lease.cleanup()
        self.assertEqual(2, attempts)

    def test_live_listener_cannot_be_unlinked(self):
        self.lease.install()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(self.socket_path))
            sock.listen(1)
            os.chmod(self.socket_path, 0o600)
            with self.assertRaisesRegex(SocketLeaseError, "live listener"):
                self.lease.cleanup()
            self.assertTrue(self.socket_path.exists())
            self.assertTrue(self.lease.dropin.exists())
        self.lease.cleanup()


if __name__ == "__main__":
    unittest.main()
