"""Native recipe target changes pass through canonical MAIN/MIX and safety bounds."""
import tempfile
import unittest
from dataclasses import replace

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import select_native_recipe_version


class _NoHardware:
    pass


def controller(profile):
    host = create_production_charge_host(_NoHardware())
    host.start(profile, 72)
    host._v2_intent = ChargeIntent.NORMAL
    return host


class NativeTargetOverrideTests(unittest.TestCase):
    def test_pinned_efb_main_and_mix_targets_are_used_only_for_selected_host(self):
        with tempfile.TemporaryDirectory() as root:
            store = NativeRecipeDraftLibrary(root)
            store.save("copy", 1, {
                "schema": 1, "execution_kind": "native_authority",
                "base_recipe_id": "native_efb_normal",
                "overrides": {
                    "charge.main.efb_voltage_v": 14.6,
                    "charge.main.current_c_rate": 0.05,
                    "charge.mix.efb_voltage_v": 15.5,
                    "charge.mix.current_c_rate": 0.02,
                },
            })
            pinned = select_native_recipe_version(
                store, "copy", 1, profile="EFB", intent="normal")
            original = controller("EFB")
            edited = controller("EFB")
            edited._native_recipe_session_selection = pinned
            base_main = original._main_target(25.0)
            custom_main = edited._main_target(25.0)
            base_mix = original._mix_target(25.0)
            custom_mix = edited._mix_target(25.0)
            self.assertAlmostEqual(custom_main[0] - base_main[0], -0.2)
            self.assertLess(custom_main[1], base_main[1])
            self.assertAlmostEqual(custom_mix[0] - base_mix[0], -1.0)
            self.assertLess(custom_mix[1], base_mix[1])
            store.save("copy", 2, {
                "schema": 1, "execution_kind": "native_authority",
                "base_recipe_id": "native_efb_normal",
                "overrides": {"charge.main.efb_voltage_v": 14.4},
            })
            self.assertEqual(edited._main_target(25.0), custom_main)

    def test_missing_selection_preserves_unchanged_stage_targets_all_profiles(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            with self.subTest(profile=profile):
                old = controller(profile)
                new = controller(profile)
                new._native_recipe_session_selection = None
                self.assertEqual(old._main_target(25.0), new._main_target(25.0))
                self.assertEqual(old._mix_target(25.0), new._mix_target(25.0))

    def test_wrong_session_profile_never_evaluates_override(self):
        with tempfile.TemporaryDirectory() as root:
            store = NativeRecipeDraftLibrary(root)
            store.save("copy", 1, {
                "schema": 1, "execution_kind": "native_authority",
                "base_recipe_id": "native_efb_normal", "overrides": {},
            })
            selection = select_native_recipe_version(
                store, "copy", 1, profile="EFB", intent="normal")
            agm = controller("AGM")
            agm._native_recipe_session_selection = selection
            with self.assertRaises(ValueError):
                agm._main_target(25.0)
            with self.assertRaises(ValueError):
                agm._mix_target(25.0)
            efb = controller("EFB")
            efb._v2_intent = ChargeIntent.DIAGNOSTIC
            efb._native_recipe_session_selection = selection
            with self.assertRaises(ValueError):
                efb._main_target(25.0)

