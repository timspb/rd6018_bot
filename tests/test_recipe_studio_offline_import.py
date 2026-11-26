"""RS-1B offline Recipe Studio saves through the existing owner, no device IO."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.recipe_studio_import import (
    inspect_step_document, publish_step_document,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "recipe_studio_offline.py"


def document(*, name="studio", version=1, voltage=14.7, action="set"):
    return {
        "id": name, "version": version,
        "steps": [
            {"action": action, "params": {"voltage_v": voltage, "current_a": 2.0}
             if action == "set" else {}, "until": {"after_seconds": 20}},
            {"action": "off", "params": {}, "until": {"after_seconds": 5}},
            {"action": "wait", "params": {}, "until": {"after_seconds": 10}},
        ],
    }


class StudioImportTests(unittest.TestCase):
    def test_offline_check_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "recipe.json"
            candidate.write_text(json.dumps(document()), encoding="utf-8")
            p = subprocess.run(
                [sys.executable, str(CLI), "check", "--file", str(candidate)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            summary = json.loads(p.stdout)
            self.assertEqual(summary["status"], "VALIDATED")
            self.assertTrue(summary["start_eligible_structure"])
            self.assertFalse(summary["physical_start_authorized"])
            self.assertEqual(list(root.iterdir()), [candidate])

    def test_save_same_library_and_reload_immutable_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            library = RecipeLibrary(Path(temp) / "recipes",
                                    max_voltage_v=15.5, max_current_a=7.2)
            result1 = publish_step_document(library, document())
            result2 = publish_step_document(library, document(version=2, voltage=14.8))
            self.assertEqual(library.versions("studio"), (1, 2))
            self.assertEqual(library.load("studio", 1).digest, result1.recipe.digest)
            self.assertEqual(library.load("studio", 2).digest, result2.recipe.digest)
            self.assertNotEqual(result1.recipe.digest, result2.recipe.digest)

    def test_stale_and_skipped_revision_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            lib = RecipeLibrary(temp, max_voltage_v=15.5, max_current_a=7.2)
            publish_step_document(lib, document())
            for version in (1, 3):
                with self.assertRaisesRegex(ValueError, "stale/skipped"):
                    publish_step_document(lib, document(version=version))
            self.assertEqual(lib.versions("studio"), (1,))

    def test_archive_and_existing_content_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            lib = RecipeLibrary(temp, max_voltage_v=15.5, max_current_a=7.2)
            publish_step_document(lib, document())
            source = Path(temp) / "studio" / "v1.json"
            data = source.read_bytes()
            (source.parent / ".archived").write_text("archived")
            with self.assertRaisesRegex(ValueError, "archived"):
                publish_step_document(lib, document(version=2))
            self.assertEqual(source.read_bytes(), data)

    def test_native_visual_drafts_and_unknown_fields_rejected(self):
        visual = {"schema": "rd6018.recipe_visual_draft.v1", "name": "x",
                  "stages": [{"kind": "native"}]}
        with self.assertRaisesRegex(ValueError, "expected only"):
            inspect_step_document(visual, max_voltage_v=15.5, max_current_a=7.2)
        unknown = dict(document(), hidden_field="ignored")
        with self.assertRaisesRegex(ValueError, "expected only"):
            inspect_step_document(unknown, max_voltage_v=15.5, max_current_a=7.2)

    def test_preflight_wait_and_hardware_ceiling(self):
        bad = document(voltage=16)
        with self.assertRaisesRegex(ValueError, "ceiling"):
            inspect_step_document(bad, max_voltage_v=15.5, max_current_a=7.2)
        bad = document()
        bad["steps"] = [bad["steps"][0], bad["steps"][-1]]
        with self.assertRaisesRegex(ValueError, "WAIT"):
            inspect_step_document(bad, max_voltage_v=15.5, max_current_a=7.2)

    def test_off_first_draft_is_not_start_eligible(self):
        result = inspect_step_document(
            document(action="off"), max_voltage_v=15.5, max_current_a=7.2)
        self.assertFalse(result.start_eligible)

    def test_save_cli_operates_only_on_explicit_library_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "export.json"
            candidate.write_text(json.dumps(document()), encoding="utf-8")
            target = root / "chosen-library"
            cmd = [sys.executable, str(CLI), "save", "--file", str(candidate),
                   "--library-root", str(target)]
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["status"], "SAVED")
            self.assertTrue((target / "studio" / "v1.json").is_file())
            again = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)
            self.assertEqual(json.loads(again.stderr)["status"], "REJECTED")

    def test_nonfinite_json_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "bad.json"
            candidate.write_text(json.dumps(document()).replace("14.7", "NaN"),
                                 encoding="utf-8")
            p = subprocess.run([sys.executable, str(CLI), "check",
                                "--file", str(candidate)], cwd=ROOT,
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(json.loads(p.stderr)["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
