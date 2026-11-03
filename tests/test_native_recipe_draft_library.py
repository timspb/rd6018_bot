"""Durable native draft versions cannot rewrite production presets."""
import json
from pathlib import Path
import tempfile
import unittest

from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters


def document(recipe_id, overrides=None):
    return {"schema": 1, "base_recipe_id": recipe_id,
            "execution_kind": "native_authority", "overrides": overrides or {}}


class NativeRecipeDraftLibraryTests(unittest.TestCase):
    def test_create_revise_and_reload_without_mutating_canonical_source(self):
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(Path(temp) / "native_drafts")
            recipe = "native_efb_normal"
            original_spec = native_recipe_parameters(recipe)[0]
            self.assertEqual(store.list_drafts(), ())
            first = store.save("my_efb", 1, document(recipe))
            second = store.save("my_efb", 2, document(
                recipe, {original_spec.key: original_spec.default}))
            self.assertEqual(store.versions("my_efb"), (1, 2))
            self.assertEqual(store.list_drafts(), ("my_efb",))
            self.assertEqual(store.load("my_efb", 1), first)
            self.assertEqual(store.load("my_efb", 2), second)
            self.assertEqual(original_spec.default,
                             native_recipe_parameters(recipe)[0].default)

    def test_published_versions_are_immutable_and_source_identity_sticks(self):
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(temp)
            store.save("copied", 1, document("native_ca_ca_normal"))
            with self.assertRaises((FileExistsError, ValueError)):
                store.save("copied", 1, document("native_ca_ca_normal"))
            with self.assertRaises(ValueError):
                store.save("copied", 3, document("native_ca_ca_normal"))
            with self.assertRaises(ValueError):
                store.save("copied", 2, document("native_agm_normal"))
            self.assertEqual(store.versions("copied"), (1,))

    def test_invalid_names_and_corrupted_documents_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(temp)
            for name in ("../escape", "native_ca_ca_normal", "bad space", "", "name/child"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    store.save(name, 1, document("native_ca_ca_normal"))
            store.save("valid", 1, document("native_agm_normal"))
            p = Path(temp) / "valid" / "v1.json"
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc["name"] = "other"
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load("valid", 1)

    def test_all_variants_can_be_cloned_without_actuation(self):
        from runtime.charge.programs.native_recipe_catalog import native_recipes
        with tempfile.TemporaryDirectory() as temp:
            store = NativeRecipeDraftLibrary(temp)
            for i, entry in enumerate(native_recipes()):
                with self.subTest(entry=entry.recipe_id):
                    name = f"copy_{i}"
                    store.save(name, 1, document(entry.recipe_id))
                    self.assertEqual(store.load(name, 1).base_recipe_id,
                                     entry.recipe_id)
            self.assertEqual(len(store.list_drafts()), 12)
