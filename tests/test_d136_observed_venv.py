"""Isolated D136 tests. Never access physical device."""
import json
import tempfile
import unittest
from pathlib import Path
from tools.d136_observed_venv import collect, inventory


class D136Tests(unittest.TestCase):
    def make(self, root):
        (root/"app").mkdir()
        (root/"venv"/"bin").mkdir(parents=True)
        (root/"venv"/"bin"/"python").write_text("python executable sample")
        (root/"venv"/"bin"/"python").chmod(0o755)
        (root/"venv"/"bin"/"python3").symlink_to("python")
        (root/"D090_TRANSACTION.json").write_text(json.dumps(
            {"phase": "STARTED", "transaction": "abc"}))
        (root/".deploy_sha").write_text("a"*40+"\n")

    def test_stable_observed_hash_no_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.make(root)
            a=collect(root,None)
            b=collect(root,None)
            self.assertEqual(a,b)
            self.assertEqual(a["status"], "OBSERVED_ONLY_NOT_RELEASE_ADMISSION")
            self.assertFalse(a["d090"]["candidate_inventory_present"])
            self.assertEqual(a["venv"]["symlinks"],1)
            self.assertEqual(a["venv"]["regular_files"],1)
            self.assertEqual(json.loads((root/"D090_TRANSACTION.json").read_text())["phase"],"STARTED")

    def test_modified_venv_changes_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.make(root)
            old=inventory(root/"venv")["tree_sha256"]
            (root/"venv"/"bin"/"python").write_text("modified")
            self.assertNotEqual(old,inventory(root/"venv")["tree_sha256"])

    def test_rejects_root_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"real"
            root.mkdir()
            self.make(root)
            link=Path(directory)/"link"
            link.symlink_to(root,target_is_directory=True)
            with self.assertRaises(ValueError):
                collect(link,None)

    def test_does_not_promote_missing_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.make(root)
            result=collect(root,None)
            self.assertEqual(result["d090"]["phase"],"STARTED")
            self.assertNotIn("COMMITTED",json.dumps(result))


if __name__=="__main__":
    unittest.main()
