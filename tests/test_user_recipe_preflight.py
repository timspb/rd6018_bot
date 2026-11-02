import unittest
from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_preflight import inspect_recipe


def recipe(actions):
    steps = []
    for action in actions:
        params = {"voltage_v": 14.7, "current_a": 1.0} if action == "set" else {}
        steps.append({"action": action, "params": params, "until": {"after_seconds": 2}})
    return parse_recipe({"id": "preflight", "version": 1, "steps": steps},
                        max_voltage_v=15.5, max_current_a=7.2)


class PreflightTests(unittest.TestCase):
    def test_off_then_wait_is_valid(self):
        self.assertTrue(inspect_recipe(recipe(["set", "off", "wait", "set"])).admissible_structure)

    def test_wait_while_energized_is_rejected(self):
        report = inspect_recipe(recipe(["set", "wait"]))
        self.assertFalse(report.admissible_structure)
        self.assertIn("WAIT", report.problems[0])

    def test_first_wait_is_rejected(self):
        self.assertFalse(inspect_recipe(recipe(["wait", "off"])).admissible_structure)
