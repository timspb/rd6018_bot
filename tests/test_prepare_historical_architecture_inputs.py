from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREP = load_module("prepare_historical_test_inputs", ROOT / "tools/architecture/prepare_historical_test_inputs.py")
AD004 = load_module("owner_evidence_ad004_source_root", ROOT / "tools/architecture/build_owner_evidence_ad004.py")


class HistoricalArchitecturePreparationTests(unittest.TestCase):
    def _repository(self, path: Path, *, include_source: bool = True) -> str:
        path.mkdir()
        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
        if include_source:
            (path / "auto_strategy.py").write_text('"""historical legacy module"""\n', encoding="utf-8")
        else:
            (path / "baseline.txt").write_text("baseline without inventory path\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-m", "fixture baseline"], check=True, capture_output=True)
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_deleted_candidate_path_is_analyzed_from_historical_preimage(self):
        self.assertFalse((ROOT / "auto_strategy.py").exists())
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            baseline = self._repository(repo)
            source = PREP.materialize_source_preimage(Path(temp) / "preimage", root=repo, baseline=baseline)
            self.assertTrue((source / "auto_strategy.py").is_file())
            row = {"path": "auto_strategy.py", "proposed_owner_candidate": "", "responsibility_basis": "",
                   "imports_out": "", "imports_in": "", "observed_side_effect_indicators": "",
                   "review_flags": "", "requires_architect_review": "false", "lines": "1"}
            with patch.object(AD004, "read_inventory", return_value=([], [row])):
                rows, _ = AD004.build_rows(source)
            self.assertEqual("auto_strategy.py", rows[0]["path"])
            self.assertIn("historical legacy module", rows[0]["evidence"])

    def test_missing_baseline_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            self._repository(repo)
            with self.assertRaises(subprocess.CalledProcessError):
                PREP.materialize_source_preimage(Path(temp) / "preimage", root=repo, baseline="missing-baseline")

    def test_missing_path_in_historical_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            baseline = self._repository(repo, include_source=False)
            source = PREP.materialize_source_preimage(Path(temp) / "preimage", root=repo, baseline=baseline)
            row = {"path": "auto_strategy.py", "proposed_owner_candidate": "", "responsibility_basis": "",
                   "imports_out": "", "imports_in": "", "observed_side_effect_indicators": "",
                   "review_flags": "", "requires_architect_review": "false", "lines": "1"}
            with patch.object(AD004, "read_inventory", return_value=([], [row])):
                with self.assertRaisesRegex(ValueError, "inventory production path is missing: auto_strategy.py"):
                    AD004.build_rows(source)


if __name__ == "__main__":
    unittest.main()
