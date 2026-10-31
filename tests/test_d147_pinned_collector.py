from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import d147_pinned_collector as subject


class D147PinnedCollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="d147-pin-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/"source.py"
        self.destination = self.root/"pinned"/"collector.py"
        self.source.write_bytes(b"print('read-only fixture')\n")
        self.hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.pin = patch.object(subject,"EXPECTED_SHA256",self.hash)
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def install(self):
        return subject.install(source=self.source,destination=self.destination,
                               host_check=lambda: None)

    def test_pinned_copy_is_exact_and_readonly(self):
        result=self.install()
        self.assertEqual(result["sha256"],self.hash)
        self.assertEqual(self.destination.read_bytes(),self.source.read_bytes())
        self.assertEqual(self.destination.stat().st_mode & 0o222,0)
        self.assertEqual(self.install()["sha256"],self.hash)

    def test_corrupt_existing_copy_never_overwritten(self):
        self.install()
        self.destination.write_bytes(b"tampered")
        with self.assertRaises(subject.CollectorPinError):
            self.install()
        self.assertEqual(self.destination.read_bytes(),b"tampered")

    def test_wrong_source_rejected_before_creation(self):
        with patch.object(subject,"EXPECTED_SHA256","0"*64):
            with self.assertRaises(subject.CollectorPinError):
                self.install()
        self.assertFalse(self.destination.exists())

    def test_source_symlink_refused(self):
        link=self.root/"link.py"
        link.symlink_to(self.source)
        with self.assertRaises(subject.CollectorPinError):
            subject.install(source=link,destination=self.destination,
                            host_check=lambda: None)

    def test_reject_world_writable_collector_parent(self):
        self.destination.parent.mkdir(mode=0o777)
        self.destination.parent.chmod(0o777)
        with self.assertRaises(subject.CollectorPinError):
            self.install()
        self.assertFalse(self.destination.exists())


    def test_existing_copy_under_symlink_directory_is_refused(self):
        self.install()
        link=self.root/"alias"
        link.symlink_to(self.destination.parent,target_is_directory=True)
        with self.assertRaises(subject.CollectorPinError):
            subject.install(source=self.source,destination=link/"collector.py",
                            host_check=lambda: None)


if __name__=="__main__":
    unittest.main()
