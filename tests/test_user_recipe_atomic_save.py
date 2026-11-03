import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.charge.programs.recipe_library import RecipeLibrary


def document(version=1, voltage=14.7):
    return {
        "id": "durable", "version": version,
        "steps": [{
            "action": "set",
            "params": {"voltage_v": voltage, "current_a": 1.0},
            "until": {"after_seconds": 60},
        }],
    }


class RecipeAtomicSaveTests(unittest.TestCase):
    def test_existing_version_not_overwritten_or_mutated(self):
        with tempfile.TemporaryDirectory() as root:
            library = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            library.save(document())
            path = Path(root) / "durable" / "v1.json"
            content = path.read_bytes()
            with self.assertRaises(FileExistsError):
                library.save(document(voltage=15.0))
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(list(path.parent.glob(".recipe-stage-*")), [])

    def test_failed_publication_exposes_no_partial_version(self):
        with tempfile.TemporaryDirectory() as root:
            library = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            with patch("runtime.charge.programs.recipe_library.os.link",
                       side_effect=OSError("simulated interrupted publication")):
                with self.assertRaisesRegex(OSError, "simulated interrupted"):
                    library.save(document())
            parent = Path(root) / "durable"
            self.assertFalse((parent / "v1.json").exists())
            self.assertEqual(list(parent.glob(".recipe-stage-*")), [])
            self.assertEqual(library.versions("durable"), ())
            library.save(document())
            self.assertEqual(library.versions("durable"), (1,))

    def test_successful_multiple_versions_are_loadable(self):
        with tempfile.TemporaryDirectory() as root:
            library = RecipeLibrary(root, max_voltage_v=15.5, max_current_a=7.2)
            library.save(document())
            library.save(document(version=2, voltage=14.8))
            self.assertEqual(library.versions("durable"), (1, 2))
            self.assertEqual(library.load("durable", 1).steps[0]["params"]["voltage_v"], 14.7)
            self.assertEqual(library.load("durable", 2).steps[0]["params"]["voltage_v"], 14.8)
            self.assertEqual(list((Path(root) / "durable").glob(".recipe-stage-*")), [])
