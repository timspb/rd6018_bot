import tempfile
import unittest
from pathlib import Path
from application.recipe_existing_session import prepare_existing_recipe_binding
from application.recipe_execution_adapter import RecipeExecutionIdentity
from application.execution_intent.models import SafetyContext
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary


class PrepareBindingTests(unittest.TestCase):
    def test_immutable_selection_and_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = RecipeCatalog(RecipeLibrary(directory, max_voltage_v=15.5, max_current_a=7.2))
            catalog.library.save({"id":"custom","version":1,"steps":[
                {"action":"set","params":{"voltage_v":14.7,"current_a":1.0},
                 "until":{"after_seconds":60}},
                {"action":"off","params":{},"until":{"after_seconds":1}}
            ]})
            args = dict(catalog=catalog, recipe_id="custom", version=1,
                        port=object(), identity=RecipeExecutionIdentity("s","t"),
                        safety_context=SafetyContext(), state_path=Path(directory)/"runner.json")
            binding = prepare_existing_recipe_binding(**args, voltage_ceiling_v=15.5)
            self.assertEqual(binding.session.recipe.version, 1)
            self.assertIsNone(binding.session.state.step)
            with self.assertRaisesRegex(ValueError, "ceiling"):
                prepare_existing_recipe_binding(**args, voltage_ceiling_v=14.5)
            Path(args["state_path"]).write_text("existing")
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare_existing_recipe_binding(**args, voltage_ceiling_v=15.5)
