"""D102 source-only admission boundaries; no hardware/network use."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parents[1]/"tools"))
import node104_d102_bench_admission as d102
from node104_d090_release import REQUIRED_BENCH_CASES

class D102BenchAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="d102-offline-")
        self.addCleanup(self.temp.cleanup)
        self.stage=Path(self.temp.name)/"stage"
        (self.stage/"tree").mkdir(parents=True)
        files={
            "bot.py":b"synthetic source; not a bot",
            "config/physical/esp128.yaml":b"edge_entities: {}\n",
        }
        records=[]
        with tarfile.open(self.stage/"source.tar","w") as tar:
            for name,data in files.items():
                path=self.stage/"tree"/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data)
                obj=tarfile.TarInfo(name)
                obj.size=len(data)
                import io
                tar.addfile(obj,io.BytesIO(data))
                records.append({"path":name,"size":len(data),
                                "sha256":hashlib.sha256(data).hexdigest()})
        commit="a"*40
        self.pin=d102.SourcePin(commit,d102.sha256(self.stage/"source.tar"),"")
        manifest={"node":"node104","service":"rd6018-bot",
                  "source_sha":commit,"archive_sha256":self.pin.archive_sha256,
                  "files":records}
        (self.stage/"RELEASE_MANIFEST.json").write_text(
            json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf8")
        self.pin=d102.SourcePin(commit,self.pin.archive_sha256,
                                d102.sha256(self.stage/"RELEASE_MANIFEST.json"))

    def test_integrity_only_never_releases_production(self):
        result=d102.readiness(self.stage,pin=self.pin)
        self.assertEqual(result["source"]["verified_source_files"],2)
        self.assertFalse(result["production_activation_authorized"])
        self.assertFalse(result["physical_trial_authorized_by_this_report"])
        self.assertFalse(result["d090_source_pins_match"])
        self.assertEqual(set(result["physical_case_status"]),set(REQUIRED_BENCH_CASES))
        self.assertTrue(all(state.startswith("OPEN_") for state in result["physical_case_status"].values()))

    def test_extra_or_modified_extracted_file_fails(self):
        p=self.stage/"tree"/"bot.py"
        p.write_text("tampered")
        with self.assertRaisesRegex(d102.AdmissionError,"extracted tree"):
            d102.readiness(self.stage,pin=self.pin)

    def test_extra_file_rejected(self):
        (self.stage/"tree"/"extra.txt").write_text("something")
        with self.assertRaisesRegex(d102.AdmissionError,"extracted tree"):
            d102.readiness(self.stage,pin=self.pin)

    def test_tampered_manifest_or_archive_rejected_by_reviewed_pins(self):
        with (self.stage/"source.tar").open("ab") as f:f.write(b"x")
        with self.assertRaisesRegex(d102.AdmissionError,"immutable pins"):
            d102.readiness(self.stage,pin=self.pin)

    def test_wrong_source_identity_rejected(self):
        wrong=d102.SourcePin("b"*40,self.pin.archive_sha256,self.pin.manifest_sha256)
        with self.assertRaisesRegex(d102.AdmissionError,"identity mismatch"):
            d102.readiness(self.stage,pin=wrong)

    def test_directory_symlink_rejected(self):
        import shutil
        shutil.rmtree(self.stage/"tree")
        (self.stage/"tree").symlink_to(Path(self.temp.name),target_is_directory=True)
        with self.assertRaisesRegex(d102.AdmissionError,"unsafe"):
            d102.readiness(self.stage,pin=self.pin)

if __name__=="__main__":unittest.main()
