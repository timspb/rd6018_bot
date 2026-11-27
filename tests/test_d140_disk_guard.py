from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.d140_disk_guard import (
    assess, require_capacity, allocated_bytes, CapacityBlocked,
    RESERVE_BYTES, OVERHEAD_BYTES,
)


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
        with patch("tools.d140_disk_guard.shutil.disk_usage",
                   return_value=SimpleNamespace(free=required)) as usage:
            self.assertTrue(assess(self.root, self.root / "candidate")["capacity_pass"])
        usage.assert_called_once_with(self.root)

    def test_candidate_symlink_refused(self):
        link = self.root / "link"
        is_symlink = Path.is_symlink

        def is_symlink_with_candidate_link(path):
            return path == link or is_symlink(path)

        with patch.object(Path, "is_symlink", is_symlink_with_candidate_link):
            with self.assertRaisesRegex(CapacityBlocked, "root or candidate unsafe"):
                require_capacity(self.root, link)

    def test_app_symlink_refused(self):
        app = self.root / "app"
        is_symlink = Path.is_symlink

        def is_symlink_with_app_link(path):
            return path == app or is_symlink(path)

        with patch.object(Path, "is_symlink", is_symlink_with_app_link):
            with self.assertRaisesRegex(CapacityBlocked, "installed component missing or symlinked"):
                allocated_bytes(app)

    def test_windows_allocation_api_value_is_used_without_st_blocks(self):
        app_file = self.root / "app" / "bot.py"
        with patch("tools.d140_disk_guard.os.name", "nt"), \
             patch("tools.d140_disk_guard._windows_allocated_bytes", return_value=8192) as api:
            self.assertEqual(allocated_bytes(self.root / "app"), 8192)
        api.assert_called_once_with(app_file)

    def test_windows_allocation_failure_fails_closed(self):
        app_file = self.root / "app" / "bot.py"
        with patch("tools.d140_disk_guard.os.name", "nt"), \
             patch("tools.d140_disk_guard._windows_allocated_bytes",
                   side_effect=CapacityBlocked("cannot reliably determine allocated file size")):
            with self.assertRaisesRegex(CapacityBlocked, "reliably determine"):
                allocated_bytes(self.root / "app")

    def test_linux_keeps_st_blocks_accounting(self):
        app_file = self.root / "app" / "bot.py"
        real_stat = Path.stat

        def stat_with_controlled_blocks(path, *args, **kwargs):
            if path == app_file:
                return SimpleNamespace(
                    st_blocks=7,
                    st_mode=real_stat(path, *args, **kwargs).st_mode,
                )
            return real_stat(path, *args, **kwargs)

        with patch("tools.d140_disk_guard.os.name", "posix"), \
             patch.object(Path, "stat", stat_with_controlled_blocks):
            self.assertEqual(allocated_bytes(self.root / "app"), 7 * 512)


if __name__ == "__main__":
    unittest.main()
