from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RUNNER_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_b889_windows_acceptance.py"
SPEC = importlib.util.spec_from_file_location("b915_windows_acceptance_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(RUNNER)


class WindowsAcceptanceRunnerTests(unittest.TestCase):
    def test_checkout_reference_accepts_current_candidate_and_rejects_other_checkout(self):
        self.assertIsNone(RUNNER._checkout_reference(f"{RUNNER.ROOT}\\tools"))
        self.assertIsNotNone(RUNNER._checkout_reference(f"{RUNNER.ROOT}-sibling\\tools"))
        foreign = RUNNER._checkout_reference(r"E:\CODEX\My_Local\rd6018-b905-win-20261125\tests")
        self.assertIsNotNone(foreign)
        self.assertIn("rd6018-b905-win", foreign)

    def test_runtime_contamination_rejects_foreign_sys_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            root.mkdir()
            with patch.object(RUNNER, "ROOT", root), \
                    patch.object(RUNNER.sys, "executable", str(root / "python.exe")), \
                    patch.object(RUNNER.sys, "path", [r"E:\CODEX\rd6018-b912-win"]):
                message = RUNNER.runtime_contamination()
        self.assertIn("sys.path[0]", message)
        self.assertIn("another RD6018 checkout", message)

    def test_runtime_contamination_rejects_foreign_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "rd6018-current"
            root.mkdir()
            with patch.object(RUNNER, "ROOT", root), \
                    patch.object(RUNNER.sys, "executable", r"E:\CODEX\rd6018-b912-win\python.exe"), \
                    patch.object(RUNNER.sys, "path", [str(root / "tools")]):
                message = RUNNER.runtime_contamination()
        self.assertIn("sys.executable", message)
        self.assertIn("another RD6018 checkout", message)

    def test_runtime_contamination_reads_python312_pth_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "candidate"
            root.mkdir()
            executable_dir = Path(temporary) / "runtime"
            executable_dir.mkdir()
            executable = executable_dir / "python.exe"
            path_file = executable_dir / "python312._pth"
            original = r"E:\CODEX\My_Local\rd6018-b905-win-20261125"
            path_file.write_text(original + "\n", encoding="utf-8")
            with patch.object(RUNNER, "ROOT", root), \
                    patch.object(RUNNER.sys, "executable", str(executable)), \
                    patch.object(RUNNER.sys, "path", [str(root / "tools")]):
                message = RUNNER.runtime_contamination()
            self.assertIn("python312._pth", message)
            self.assertIn("rd6018-b905-win", message)
            self.assertEqual(path_file.read_text(encoding="utf-8"), original + "\n")

    def test_missing_historical_baseline_has_precise_preflight_error(self):
        message = RUNNER.historical_baseline_error(128)
        self.assertIn(RUNNER.HISTORICAL_BASELINE, message)
        self.assertIn("candidate Git history is incomplete", message)
        self.assertIsNone(RUNNER.historical_baseline_error(0))


if __name__ == "__main__":
    unittest.main()
