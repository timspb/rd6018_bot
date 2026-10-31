import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import d148_recovery_collector as d148


class D148RecoveryPinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d148-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pinned").mkdir(mode=0o700)
        self.old = self.root / "pinned" / "old.py"
        self.source = self.root / "new_source.py"
        self.dest = self.root / "pinned" / "recovery.py"
        self.old.write_bytes(b"old pinned proof collector")
        self.source.write_bytes(b"new recovery proof collector")
        self.old.chmod(0o400)
        self.oldhash = hashlib.sha256(self.old.read_bytes()).hexdigest()
        self.newhash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.patch_old = patch.object(d148, "D147_SHA256", self.oldhash)
        self.patch_new = patch.object(d148, "D138_SHA256", self.newhash)
        self.patch_old.start(); self.patch_new.start()
        self.addCleanup(self.patch_old.stop); self.addCleanup(self.patch_new.stop)

    def run_install(self):
        return d148.install(self.source, self.dest, self.old,
                            host_check=lambda: None)

    def test_install_exact_and_repeat_idempotent(self):
        value = self.run_install()
        self.assertEqual(value["sha256"], self.newhash)
        self.assertEqual(self.dest.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.dest.stat().st_mode & 0o222, 0)
        self.assertEqual(self.run_install()["sha256"], self.newhash)
        self.assertEqual(self.old.read_bytes(), b"old pinned proof collector")

    def test_wrong_new_source_refuses_without_writing(self):
        self.source.write_bytes(b"unreviewed")
        with self.assertRaises(d148.RecoveryCollectorError):
            self.run_install()
        self.assertFalse(self.dest.exists())

    def test_old_pin_drift_refuses_without_writing(self):
        self.old.chmod(0o600)
        self.old.write_bytes(b"changed")
        self.old.chmod(0o400)
        with self.assertRaises(d148.RecoveryCollectorError):
            self.run_install()
        self.assertFalse(self.dest.exists())

    def test_existing_corrupt_destination_never_overwritten(self):
        self.run_install()
        self.dest.chmod(0o600)
        self.dest.write_bytes(b"tampered")
        self.dest.chmod(0o400)
        with self.assertRaises(d148.RecoveryCollectorError):
            self.run_install()
        self.assertEqual(self.dest.read_bytes(), b"tampered")

    def test_symlink_destination_refused(self):
        self.dest.symlink_to(self.source)
        with self.assertRaises(d148.RecoveryCollectorError):
            self.run_install()


if __name__ == "__main__":
    unittest.main()
