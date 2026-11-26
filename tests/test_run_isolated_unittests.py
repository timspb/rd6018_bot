from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RUNNER_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_isolated_unittests.py"
SPEC = importlib.util.spec_from_file_location("run_isolated_unittests", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(RUNNER)


class IsolatedUnittestRunnerTests(unittest.TestCase):
    def test_interpreter_must_be_addressed_inside_candidate_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            root.mkdir()
            exe = root / ".venv" / "Scripts" / "python.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            self.assertEqual(RUNNER._candidate_interpreter(str(exe), root), exe)
            foreign = Path(temporary) / "foreign-python.exe"
            foreign.touch()
            with self.assertRaisesRegex(ValueError, "inside candidate root"):
                RUNNER._candidate_interpreter(str(foreign), root)

    def test_candidate_local_embedded_runtime_pth_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            exe = root / ".runtime" / "python312" / "python.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            path_file = exe.parent / "python312._pth"
            original = (
                "# candidate-local embedded runtime\n.\n../..\n"
                "../../tools\n../../tests\n" + str(root / "tests") + "\nimport site\n"
            )
            path_file.write_text(original, encoding="utf-8")
            self.assertEqual(RUNNER._candidate_interpreter(str(exe), root), exe)
            self.assertEqual(path_file.read_text(encoding="utf-8"), original)

    def test_pth_foreign_or_outside_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            exe = root / ".runtime" / "python312" / "python.exe"
            exe.parent.mkdir(parents=True)
            exe.touch()
            path_file = exe.parent / "python312._pth"
            for outside in ("../../../..", "E:/another/checkout", "..\\..\\..\\foreign"):
                with self.subTest(entry=outside):
                    path_file.write_text(f"{outside}\n", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "outside candidate root|malformed _pth"):
                        RUNNER._candidate_interpreter(str(exe), root)

    def test_pth_rejects_unrecognized_import_directives(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / "python.exe"
            exe.touch()
            (root / "python312._pth").write_text("import site\nimport os\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "malformed or unsupported"):
                RUNNER._candidate_interpreter(str(exe), root)

    def test_environment_scrubs_python_path_and_home_case_insensitively(self):
        with patch.dict("os.environ", {"PYTHONPATH": "foreign", "pythonhome": "foreign-home", "TG_TOKEN": "test"}, clear=True):
            env = RUNNER._clean_env()
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("pythonhome", env)
        self.assertEqual(env["TG_TOKEN"], "test")

    def test_history_copy_transfers_packed_git_objects_and_verifies_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                            "commit", "--allow-empty", "-qm", "baseline"], check=True)
            baseline = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(source), "gc", "--prune=now"], check=True)
            disposable = root / "disposable"
            disposable.mkdir()
            subprocess.run(["git", "init", "-q", str(disposable)], check=True)
            with patch.object(RUNNER, "HISTORICAL_BASELINE", baseline):
                RUNNER._prepare_history(disposable, source / ".git" / "objects")
            copied = subprocess.check_output(["git", "-C", str(disposable), "cat-file", "-t", baseline], text=True)
            self.assertEqual(copied.strip(), "commit")
            self.assertTrue(any((disposable / ".git" / "objects" / "pack").glob("*.pack")))


if __name__ == "__main__":
    unittest.main()
