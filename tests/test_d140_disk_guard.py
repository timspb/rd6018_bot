from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from tools.d140_disk_guard import assess, require_capacity, CapacityBlocked, RESERVE_BYTES, OVERHEAD_BYTES


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="d140-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "installed"
        self.root.mkdir()
        (self.root / "app").mkdir()
        (self.root / "venv").mkdir()
        (self.root / "candidate").mkdir()
        (self.root / "app" / "bot.py").write_bytes(b"old")
        (self.root / "venv" / "python").write_bytes(b"old venv")

    def test_low_space_blocks(self):
        before = {p.as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(CapacityBlocked, "before service stop"):
            require_capacity(self.root, self.root / "candidate",
                             disk_usage=lambda _: SimpleNamespace(free=RESERVE_BYTES))
        self.assertEqual(before, {p.as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_capacity_pass_only_above_full_required(self):
        initial = assess(self.root, self.root / "candidate",
                         disk_usage=lambda _: SimpleNamespace(free=0))
        required = initial["minimum_free_bytes"]
        self.assertGreaterEqual(required, RESERVE_BYTES + OVERHEAD_BYTES)
        self.assertFalse(assess(self.root, self.root / "candidate",
                                disk_usage=lambda _: SimpleNamespace(free=required-1))["capacity_pass"])
        self.assertTrue(require_capacity(self.root, self.root / "candidate",
                                disk_usage=lambda _: SimpleNamespace(free=required))["capacity_pass"])

    def test_candidate_symlink_refused(self):
        link = self.root / "link"
        link.symlink_to(self.root / "candidate", target_is_directory=True)
        with self.assertRaises(CapacityBlocked):
            require_capacity(self.root, link)

    def test_app_symlink_refused(self):
        (self.root / "app" / "external").symlink_to(self.root / "venv" / "python")
        result = assess(self.root, self.root / "candidate",
                        disk_usage=lambda _: SimpleNamespace(free=2**40))
        self.assertTrue(result["capacity_pass"])


if __name__ == "__main__":
    unittest.main()
