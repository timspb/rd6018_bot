"""Native recipe selection flows into existing START without hardware access."""
import tempfile
import types
from pathlib import Path
from unittest.mock import patch
import unittest

from pb_domain import ChargeIntent
from runtime.safety.output_policy import EnableResult
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from application.start_transaction_service import start_profile_transactional
from test_start_transaction_service import FakeApp, FakeMessage, PENDING


class NativeSelectionStartTests(unittest.IsolatedAsyncioTestCase):
    def _prepared(self, root):
        app = FakeApp(EnableResult(enabled=True))
        catalog = RecipeCatalog(RecipeLibrary(
            Path(root) / "user_recipes", max_voltage_v=15.5, max_current_a=7.2,
        ))
        app._user_recipe_catalog = catalog
        lib = NativeRecipeDraftLibrary(Path(root) / "native_recipe_drafts")
        lib.save("my_efb", 1, {
            "schema": 1, "base_recipe_id": "native_efb_recovery",
            "execution_kind": "native_authority",
            "overrides": {"charge.main.efb_voltage_v": 14.6},
        })
        return app, lib

    async def test_valid_copy_pinned_before_initial_target_without_second_runner(self):
        with tempfile.TemporaryDirectory() as root:
            app, lib = self._prepared(root)
            pending = types.SimpleNamespace(**vars(PENDING),
                native_recipe_name="my_efb", native_recipe_version=1)
            observed = []
            original_main = app.charge_controller._main_target
            def capture(temp):
                selection = app.charge_controller._native_recipe_session_selection
                observed.append(selection)
                return original_main(temp)
            app.charge_controller._main_target = capture
            message = FakeMessage()
            ok = await start_profile_transactional(app, message, pending)
            self.assertTrue(ok)
            self.assertEqual(len(observed), 1)
            self.assertEqual(observed[0].version, 1)
            self.assertEqual(observed[0].base_recipe_id,
                             "native_efb_recovery")
            self.assertIsNone(app.charge_controller._existing_recipe_execution_binding)
            lib.save("my_efb", 2, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority",
                "overrides": {"charge.main.efb_voltage_v": 14.5},
            })
            self.assertEqual(observed[0],
                             app.charge_controller._native_recipe_session_selection)

    async def test_wrong_intent_or_missing_version_rejected_before_controller_start(self):
        with tempfile.TemporaryDirectory() as root:
            app, _ = self._prepared(root)
            for name, version in (("my_efb", 99), ("missing", 1)):
                app.charge_controller.started = False
                message = FakeMessage()
                pending = types.SimpleNamespace(
                    **vars(PENDING), native_recipe_name=name,
                    native_recipe_version=version)
                self.assertFalse(await start_profile_transactional(
                    app, message, pending))
                self.assertFalse(app.charge_controller.started)
                self.assertIsNone(app.hass.enable_kwargs)
            app.charge_controller.started = False
            message = FakeMessage()
            pending = types.SimpleNamespace(
                **{**vars(PENDING), "intent": ChargeIntent.DIAGNOSTIC},
                native_recipe_name="my_efb", native_recipe_version=1)
            self.assertFalse(await start_profile_transactional(
                app, message, pending))
            self.assertFalse(app.charge_controller.started)
            self.assertIsNone(app.hass.enable_kwargs)

    async def test_ordinary_auto_never_selects_an_old_copy(self):
        with tempfile.TemporaryDirectory() as root:
            app, _ = self._prepared(root)
            app.charge_controller._native_recipe_session_selection = object()
            message = FakeMessage()
            self.assertTrue(await start_profile_transactional(app, message, PENDING))
            self.assertIsNone(app.charge_controller._native_recipe_session_selection)
