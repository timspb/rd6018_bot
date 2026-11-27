"""Native Recipe Studio contract: typed draft and production-supported overrides."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.recipe_studio_import import (
    inspect_native_document, publish_native_document,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "recipe_studio_offline.py"


def native_doc(name="my_efb", version=1, base="native_efb_normal", overrides=None):
    return {"name": name, "version": version,
            "draft": {"schema": 1, "base_recipe_id": base,
                      "execution_kind": "native_authority",
                      "overrides": {} if overrides is None else overrides}}


class NativeStudioImportTests(unittest.TestCase):
    def test_valid_draft_copy_and_immutable_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(temp)
            first = publish_native_document(store, native_doc())
            second = publish_native_document(store, native_doc(version=2, overrides={
                "charge.main.efb_voltage_v": 14.6}))
            self.assertEqual(store.versions("my_efb"), (1, 2))
            self.assertEqual(store.load("my_efb", 1), first.draft)
            self.assertEqual(store.load("my_efb", 2), second.draft)
            self.assertNotEqual(first.draft.overrides, second.draft.overrides)

    def test_stale_version_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(temp)
            publish_native_document(store, native_doc())
            with self.assertRaises((ValueError, FileExistsError)):
                publish_native_document(store, native_doc())
            with self.assertRaises(ValueError):
                publish_native_document(store, native_doc(version=3))

    def test_mismatched_parent_for_revision_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(temp)
            publish_native_document(store, native_doc())
            with self.assertRaises(ValueError):
                publish_native_document(store, native_doc(version=2,
                                                          base="native_agm_normal"))

    def test_invalid_override_or_schema_refused_before_save(self):
        for override in ({"not.real": 1.0},
                         {"charge.main.efb_voltage_v": 100.0},
                         {"charge.main.efb_voltage_v": "14.6"},
                         {"charge.main.current_c_rate": 0.11}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                inspect_native_document(native_doc(overrides=override))

    def test_invalid_id_and_unknown_fields_refused(self):
        for name in ("native_efb_normal", "../escape", "has space"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect_native_document(native_doc(name=name))
        with self.assertRaisesRegex(ValueError, "expected only"):
            inspect_native_document(dict(native_doc(), hidden=True))

    def test_cli_check_and_save_without_device_or_implicit_library(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "draft.json"
            source.write_text(json.dumps(native_doc()), encoding="utf-8")
            check = subprocess.run(
                [sys.executable, str(CLI), "check-native", "--file", str(source)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(json.loads(check.stdout)["kind"], "native_draft")
            self.assertEqual(list(root.iterdir()), [source])

            target = root / "chosen-native-library"
            saved = subprocess.run(
                [sys.executable, str(CLI), "save-native", "--file", str(source),
                 "--library-root", str(target)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertFalse(json.loads(saved.stdout)["physical_start_authorized"])
            self.assertEqual(NativeRecipeDraftLibrary(target).versions("my_efb"), (1,))


if __name__ == "__main__":
    unittest.main()
