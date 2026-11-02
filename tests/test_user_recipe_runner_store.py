import tempfile
import unittest
from pathlib import Path
from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_runner import RunnerState, tick
from runtime.charge.programs.recipe_runner_store import save_runner, load_runner


class RunnerStoreTests(unittest.TestCase):
    def test_pending_roundtrip_and_revision_pin(self):
        recipe = parse_recipe({"id": "test", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1},
             "until": {"after_seconds": 10}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        pending = tick(recipe, RunnerState(), now_s=100, measurements={}).state
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner.json"
            save_runner(path, recipe, pending)
            self.assertEqual(load_runner(path, recipe), pending)
            revised = parse_recipe({"id": "test", "version": 2, "steps": [
                {"action": "off", "params": {}, "until": {"after_seconds": 1}},
            ]}, max_voltage_v=15.5, max_current_a=7.2)
            with self.assertRaises(ValueError):
                load_runner(path, revised)
            data = path.read_text(encoding="utf-8")
            path.write_text(data.replace(pending.pending.action_id, "fake"), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_runner(path, recipe)
