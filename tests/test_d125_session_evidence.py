import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.node104_d125_session_evidence import inspect_session,SessionEvidenceError

class D125SessionEvidenceTests(unittest.TestCase):
    def test_legacy_active_document_remains_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"session.json"
            p.write_text(json.dumps({"stage":"Main Charge","v2_trace_session_id":"abc","v2_battery_id":"sample"}))
            a=inspect_session(p)
            self.assertEqual(a["classification"],"preserved_nonterminal")
            self.assertFalse(a["mutation_authorized"])
            self.assertFalse(a["safe_to_auto_resume"])
    def test_empty_unknown_document_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"session.json";p.write_text("{}")
            self.assertEqual(inspect_session(p)["classification"],"unknown_blocked")
    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            q=Path(folder)/"link.json"
            with patch.object(Path, "is_symlink", autospec=True,
                              side_effect=lambda path: path == q):
                with self.assertRaises(SessionEvidenceError):inspect_session(q)
