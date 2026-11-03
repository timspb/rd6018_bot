"""An accepted recipe version stays pinned across later revisions."""
from dataclasses import FrozenInstanceError, replace
import tempfile
import unittest

from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import (
    NativeRecipeSessionSelection, select_native_recipe_version,
)


def document(base, overrides=None):
    return {"schema": 1, "execution_kind": "native_authority",
            "base_recipe_id": base, "overrides": overrides or {}}


class NativeRecipeSessionTests(unittest.TestCase):
    def test_snapshot_is_stable_across_future_versions_and_library_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            lib = NativeRecipeDraftLibrary(directory)
            lib.save("my_efb", 1, document("native_efb_normal",
                     {"charge.main.efb_voltage_v": 14.6}))
            first = select_native_recipe_version(
                lib, "my_efb", 1, profile="EFB", intent="normal")
            lib.save("my_efb", 2, document("native_efb_normal",
                     {"charge.main.efb_voltage_v": 14.5}))
            second = select_native_recipe_version(
                lib, "my_efb", 2, profile="EFB", intent="normal")
            self.assertNotEqual(first.content_sha256, second.content_sha256)
            self.assertEqual(dict(first.overrides)["charge.main.efb_voltage_v"],14.6)
            self.assertEqual(
                NativeRecipeSessionSelection.from_document(first.to_document()),
                first)
            with self.assertRaises(FrozenInstanceError):
                first.version = 9

    def test_ignored_production_parameters_cannot_be_selected_for_start(self):
        with tempfile.TemporaryDirectory() as directory:
            lib = NativeRecipeDraftLibrary(directory)
            variants = (
                ("native_agm_normal", "charge.main.default_voltage_v", 14.6),
                ("native_efb_normal", "charge.main.current_c_rate", 0.20),
            )
            for number, (recipe, key, value) in enumerate(variants):
                name = f"copy_{number}"
                lib.save(name, 1, document(recipe, {key: value}))
                with self.subTest(recipe=recipe, key=key):
                    with self.assertRaises(ValueError):
                        select_native_recipe_version(
                            lib, name, 1,
                            profile="AGM" if recipe.startswith("native_agm")
                                    else "EFB",
                            intent="normal",
                        )

    def test_wrong_profile_intent_and_tampered_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            lib = NativeRecipeDraftLibrary(directory)
            lib.save("sample", 1, document("native_ca_ca_recovery"))
            for profile, intent in (("AGM","recovery"), ("Ca/Ca","normal"),
                                    ("Custom","recovery")):
                with self.subTest(profile=profile, intent=intent):
                    with self.assertRaises(ValueError):
                        select_native_recipe_version(
                            lib,"sample",1,profile=profile,intent=intent)
            selected = select_native_recipe_version(
                lib,"sample",1,profile="Ca/Ca",intent="recovery")
            for k,v in (("profile","AGM"), ("intent","diagnostic"),
                        ("version",2), ("name","other"),
                        ("content_sha256","wrong")):
                changed = selected.to_document()
                changed[k] = v
                with self.subTest(field=k),self.assertRaises(ValueError):
                    NativeRecipeSessionSelection.from_document(changed)
