"""Temporary session writer descriptor ownership on Windows-compatible paths."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.charge import session_atomic


class SessionAtomicDescriptorOwnershipTests(unittest.TestCase):
    def test_missing_fchmod_uses_path_mode_and_replaces_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "session.json"
            target.write_text('{"old": true}', encoding="utf-8")

            with patch.object(session_atomic.os, "fchmod", None, create=True):
                session_atomic.atomic_session_write(target, {"new": True})

            self.assertEqual(target.read_text(encoding="utf-8"), '{\n  "new": true\n}')
            self.assertEqual(list(Path(directory).glob(".charge-session-*.tmp")), [])

    def test_fdopen_failure_closes_still_owned_descriptor_before_unlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "session.json"
            target.write_text('{"old": true}', encoding="utf-8")
            real_mkstemp = tempfile.mkstemp
            created = {}

            def record_mkstemp(*args, **kwargs):
                fd, name = real_mkstemp(*args, **kwargs)
                created["fd"] = fd
                created["name"] = name
                return fd, name

            with patch.object(session_atomic.tempfile, "mkstemp", side_effect=record_mkstemp), \
                 patch.object(session_atomic.os, "fdopen", side_effect=OSError("fdopen failed")):
                with self.assertRaisesRegex(OSError, "fdopen failed"):
                    session_atomic.atomic_session_write(target, {"new": True})

            with self.assertRaises(OSError):
                os.fstat(created["fd"])
            self.assertFalse(Path(created["name"]).exists())
            self.assertEqual(target.read_text(encoding="utf-8"), '{"old": true}')


if __name__ == "__main__":
    unittest.main()
