from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.d138_candidate_preflight import inspect_candidate

SOURCE="d351c208cbf8666f881a4660df6a0b211170e857"
PREIMAGE="f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c"


class D138CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"live"
        self.stage=Path(self.tmp.name)/"stage"
        self.root.mkdir()
        (self.stage/"tree").mkdir(parents=True)
        f=self.stage/"tree"/"bot.py"
        f.write_bytes(b"candidate")
        f.chmod(0o644)
        entry={"path":"bot.py","sha256":hashlib.sha256(b"candidate").hexdigest(),
               "size":9,"mode":0o644}
        (self.stage/"RELEASE_MANIFEST.json").write_text(json.dumps({
            "schema":"D138_STAGED_SOURCE_V1","source_sha":SOURCE,
            "source_archive_sha256":"a"*64,"files":1,"manifest_entries":[entry]}))
        (self.stage/"venv"/"bin").mkdir(parents=True)
        (self.stage/"venv"/"bin"/"python").write_text("fixture")

    def run_preflight(self, *, preimage=PREIMAGE, installed=True):
        def subproc(cmd,**kw):
            if "-m" in cmd:return SimpleNamespace(returncode=0,stdout="No broken requirements found.")
            return SimpleNamespace(returncode=0,stdout="(3, 11)\n")
        with patch("tools.d138_candidate_preflight.observed_preimage",return_value={"preimage_sha256":preimage}), \
             patch("tools.d138_candidate_preflight.inventory_venv",return_value={"regular_files":101,"tree_sha256":"b"*64}), \
             patch("tools.d138_candidate_preflight.subprocess.run",side_effect=subproc), \
             patch("tools.d138_candidate_preflight.shutil.disk_usage",return_value=SimpleNamespace(free=500*1024*1024)):
            return inspect_candidate(root=self.root,stage=self.stage,pid=123,
                                     source_sha=SOURCE,preimage_sha256=PREIMAGE)

    def test_prepared_is_never_actuation_admission(self):
        result=self.run_preflight()
        self.assertFalse(result["admitted_for_activation"])
        self.assertEqual(result["status"],"SOURCE_AND_VENV_PREPARED_NOT_ACTIVATED")
        self.assertEqual(result["source_files"],1)

    def test_live_preimage_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"preimage drift"):
            self.run_preflight(preimage="c"*64)

    def test_source_byte_corruption_fails_closed(self):
        (self.stage/"tree"/"bot.py").write_text("tampered")
        with self.assertRaisesRegex(ValueError,"byte/mode mismatch"):
            self.run_preflight()

    def test_missing_venv_fails_closed(self):
        (self.stage/"venv"/"bin"/"python").unlink()
        with self.assertRaisesRegex(ValueError,"environment incomplete"):
            self.run_preflight()


if __name__=="__main__":
    unittest.main()
