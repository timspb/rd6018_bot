import tempfile
import unittest
from unittest.mock import Mock

from application.start_recipe_selection import (
    StartRecipeSelectionFailure, resolve_start_recipe_selections,
    select_user_recipe_for_start,
)
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary


class StartRecipeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.catalog = RecipeCatalog(RecipeLibrary(
            self.directory.name, max_voltage_v=18.0, max_current_a=20.0,
        ))

    def test_selects_immutable_first_set_recipe_without_runner_or_mutation(self):
        self.catalog.library.save({"id": "chosen", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 13.8, "current_a": 1.2},
             "until": {"after_seconds": 30}},
            {"action": "off", "params": {}, "until": {"after_seconds": 1}},
        ]})
        load = Mock(wraps=self.catalog.library.load)
        self.catalog.library.load = load

        first = select_user_recipe_for_start(
            catalog=self.catalog, recipe_id="chosen", version=1,
        )
        second = select_user_recipe_for_start(
            catalog=self.catalog, recipe_id="chosen", version=1,
        )

        self.assertEqual(first, second)
        self.assertEqual(load.call_args_list, [
            unittest.mock.call("chosen", 1), unittest.mock.call("chosen", 1),
        ])
        self.assertEqual(first.steps[0]["action"], "set")
        self.assertFalse((self.catalog.library.root / "_runs").exists())

    def test_rejects_off_first_selection_before_runner_creation(self):
        self.catalog.library.save({"id": "off-first", "version": 1, "steps": [
            {"action": "off", "params": {}, "until": {"after_seconds": 1}},
            {"action": "wait", "params": {}, "until": {"after_seconds": 2}},
        ]})

        with self.assertRaisesRegex(ValueError, "первый шаг.*SET"):
            select_user_recipe_for_start(
                catalog=self.catalog, recipe_id="off-first", version=1,
            )
        self.assertFalse((self.catalog.library.root / "_runs").exists())

    def test_rejects_malformed_recipe_structure(self):
        self.catalog.library.save({"id": "bad-flow", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 13.8, "current_a": 1.2},
             "until": {"after_seconds": 30}},
            {"action": "wait", "params": {}, "until": {"after_seconds": 2}},
        ]})

        with self.assertRaisesRegex(ValueError, "WAIT must immediately follow OFF"):
            select_user_recipe_for_start(
                catalog=self.catalog, recipe_id="bad-flow", version=1,
            )

    def test_application_owner_resolves_native_pin(self):
        native = object()
        pending = Mock(recipe_id=None, recipe_version=None,
                       native_recipe_name="n", native_recipe_version=7,
                       profile="EFB", intent="normal")
        pending_before = vars(pending).copy()
        app = Mock(_user_recipe_catalog=self.catalog)
        with unittest.mock.patch(
            "application.start_recipe_selection.select_user_recipe_for_start",
        ) as select_user, unittest.mock.patch(
            "runtime.charge.programs.native_recipe_session.select_native_recipe_version",
            return_value=native,
        ) as select_native:
            selection = resolve_start_recipe_selections(app=app, pending=pending)

        self.assertIsNone(selection.selected_recipe)
        self.assertEqual(selection.selected_native, native)
        select_user.assert_not_called()
        select_native.assert_called_once()
        self.assertEqual(select_native.call_args.args[1:], ("n", 7))
        self.assertEqual(select_native.call_args.kwargs,
                         {"profile": "EFB", "intent": "normal"})
        self.assertEqual(app._user_recipe_catalog, self.catalog)
        self.assertEqual(vars(pending), pending_before)

    def test_mutually_selected_variants_reject_as_native_without_calling_native_selector(self):
        pending = Mock(recipe_id="u", recipe_version=1,
                       native_recipe_name="n", native_recipe_version=1,
                       profile="EFB", intent="normal")
        app = Mock(_user_recipe_catalog=self.catalog)
        with unittest.mock.patch(
            "application.start_recipe_selection.select_user_recipe_for_start",
            return_value=object(),
        ) as select_user, unittest.mock.patch(
            "runtime.charge.programs.native_recipe_session.select_native_recipe_version",
        ) as select_native:
            failure = resolve_start_recipe_selections(app=app, pending=pending)

        self.assertIsInstance(failure, StartRecipeSelectionFailure)
        self.assertEqual(failure.kind, "native")
        self.assertEqual(str(failure.error),
                         "native and user step recipes are mutually exclusive")
        select_user.assert_called_once()
        select_native.assert_not_called()

    def test_user_failure_keeps_user_variant_and_skips_native_lookup(self):
        pending = Mock(recipe_id="stale", recipe_version=3,
                       native_recipe_name="n", native_recipe_version=1)
        app = Mock(_user_recipe_catalog=self.catalog)
        with unittest.mock.patch(
            "application.start_recipe_selection.select_user_recipe_for_start",
            side_effect=ValueError("stale recipe"),
        ), unittest.mock.patch(
            "runtime.charge.programs.native_recipe_session.select_native_recipe_version",
        ) as select_native:
            failure = resolve_start_recipe_selections(app=app, pending=pending)

        self.assertEqual((failure.kind, type(failure.error), str(failure.error)),
                         ("user", ValueError, "stale recipe"))
        select_native.assert_not_called()

    def test_unexpected_selector_exception_is_not_swallowed(self):
        pending = Mock(recipe_id="u", recipe_version=1, native_recipe_name=None)
        app = Mock(_user_recipe_catalog=self.catalog)
        with unittest.mock.patch(
            "application.start_recipe_selection.select_user_recipe_for_start",
            side_effect=RuntimeError("unexpected"),
        ), self.assertRaisesRegex(RuntimeError, "unexpected"):
            resolve_start_recipe_selections(app=app, pending=pending)


if __name__ == "__main__":
    unittest.main()
