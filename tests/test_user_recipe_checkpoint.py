import json
import tempfile
import unittest
from pathlib import Path

from runtime.charge.programs.recipe_checkpoint import save_checkpoint, load_checkpoint
from runtime.charge.programs.recipe_engine import StepState
from runtime.charge.programs.recipe_schema import parse_recipe


def recipe(version=1):
    return parse_recipe({
        "id": "checkpoint-test", "version": version, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 2},
             "until": {"after_seconds": 10}},
            {"action": "off", "params": {}, "until": {"after_seconds": 15}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)


class CheckpointTests(unittest.TestCase):
    def test_round_trip_and_version_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            original = recipe()
            state = StepState(original.digest, 1, 42.0)
            save_checkpoint(path, original, state, output_confirmed_off=True)
            restored = load_checkpoint(path, original)
            self.assertEqual(restored.state, state)
            self.assertTrue(restored.output_confirmed_off)
            with self.assertRaises(ValueError):
                load_checkpoint(path, recipe(version=2))
    def test_corrupt_state_and_unknown_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            current = recipe()
            with self.assertRaises(ValueError):
                save_checkpoint(path, current, StepState("foreign", 0, 1),
                                output_confirmed_off=False)
            save_checkpoint(path, current, StepState(current.digest, 0, 1),
                            output_confirmed_off=False)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["step_index"] = 999
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_checkpoint(path, current)
            data["step_index"] = 0
            data["output_confirmed_off"] = "yes"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_checkpoint(path, current)
