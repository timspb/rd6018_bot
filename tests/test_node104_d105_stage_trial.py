"""D105 deterministic, tamper-evident source-only -> trial review stage tests."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools import node104_d105_stage_trial as stage


class StageTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="d105-stage-")
        self.addCleanup(self.temp.cleanup)
        self.src=Path(self.temp.name)/"d103"
        self.src.mkdir()
        self.dest=Path(self.temp.name)/"trial-stage"
        self.data={"bot.py":b"fake source not used for production",
                   "tools/guard.py":b"pass\n"}
        rows=[]
        with tarfile.open(self.src/"source.tar","w") as output:
            for key,data in self.data.items():
                item=tarfile.TarInfo(key)
                item.size=len(data)
                output.addfile(item,io.BytesIO(data))
                rows.append({"path":key,"size":len(data),
                             "sha256":hashlib.sha256(data).hexdigest()})
        archive=stage.digest(self.src/"source.tar")
        document={"type":"SOURCE_ONLY_NOT_APPROVED_FOR_DEPLOYMENT","node":"node104",
                  "commit":stage.D103_SHA,"archive_sha256":archive,
                  "tracked_files":len(rows),"source_files":rows}
        (self.src/"SOURCE_MANIFEST.json").write_text(json.dumps(document,indent=2,sort_keys=True)+"\n")
        self.archive_sha=archive
        self.manifest_sha=stage.digest(self.src/"SOURCE_MANIFEST.json")

    def run_stage(self):
        with patch.object(stage,"D103_SOURCE_MANIFEST_SHA256",self.manifest_sha), \
             patch.object(stage,"D103_SOURCE_TAR_SHA256",self.archive_sha):
            return stage.stage_trial(self.src,self.dest)

    def test_exact_artifact_is_reviewable_by_d102(self):
        pin=self.run_stage()
        proof=stage.verify_source(self.dest,pin=pin)
        self.assertEqual(proof["verified_source_files"],2)
        self.assertEqual(pin.commit,stage.D103_SHA)
        self.assertTrue((self.dest/"STAGED_OK").is_file())

    def test_archive_byte_tamper_blocks_staging(self):
        with (self.src/"source.tar").open("ab") as data:
            data.write(b"bad")
        with self.assertRaisesRegex(stage.AdmissionError,"reviewed pins"):
            self.run_stage()
        self.assertFalse(self.dest.exists())

    def test_unsafe_member_rejected_even_with_rehashed_manifest(self):
        bad=self.src/"source.tar"
        with tarfile.open(bad,"w") as tar:
            item=tarfile.TarInfo("../escape")
            item.size=1
            tar.addfile(item,io.BytesIO(b"x"))
        self.archive_sha=stage.digest(bad)
        doc=json.loads((self.src/"SOURCE_MANIFEST.json").read_text())
        doc["archive_sha256"]=self.archive_sha
        doc["source_files"]=[{"path":"../escape","size":1,
                            "sha256":hashlib.sha256(b"x").hexdigest()}]
        doc["tracked_files"]=1
        (self.src/"SOURCE_MANIFEST.json").write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
        self.manifest_sha=stage.digest(self.src/"SOURCE_MANIFEST.json")
        with self.assertRaisesRegex(stage.AdmissionError,"unsafe"):
            self.run_stage()
        self.assertFalse(self.dest.exists())

    def test_refuses_reusing_output_directory(self):
        self.dest.mkdir()
        with self.assertRaisesRegex(stage.AdmissionError,"existing destination"):
            self.run_stage()

    def test_detects_missing_or_duplicate_inventory_paths(self):
        doc=json.loads((self.src/"SOURCE_MANIFEST.json").read_text())
        doc["source_files"].append(dict(doc["source_files"][0]))
        doc["tracked_files"]+=1
        (self.src/"SOURCE_MANIFEST.json").write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
        self.manifest_sha=stage.digest(self.src/"SOURCE_MANIFEST.json")
        with self.assertRaisesRegex(stage.AdmissionError,"duplicate"):
            self.run_stage()


if __name__=="__main__":
    unittest.main()
