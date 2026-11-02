import unittest

from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_engine import evaluate_step, StepState


class RecipeEngineTests(unittest.TestCase):
    def setUp(self):
        self.recipe = parse_recipe({
            "id": "trial", "version": 1, "steps": [
                {"action": "set", "params": {"voltage_v": 14.7, "current_a": 2},
                 "until": {"voltage_gte": 13.12}},
                {"action": "off", "params": {}, "until": {"after_seconds": 10}},
                {"action": "wait", "params": {}, "until": {"voltage_lte": 12}},
            ]}, max_voltage_v=15.5, max_current_a=7.2)

    def test_step_progression_and_final_off(self):
        a = evaluate_step(self.recipe, None, now_s=100, measurements={})
        self.assertEqual(a.proposed_action, "set")
        b = evaluate_step(self.recipe, a.state, now_s=110, measurements={"voltage": 13})
        self.assertFalse(b.transitioned)
        c = evaluate_step(self.recipe, b.state, now_s=111, measurements={"voltage": 13.12})
        self.assertEqual(c.proposed_action, "off")
        self.assertEqual(c.state.step_index, 1)
        d = evaluate_step(self.recipe, c.state, now_s=120, measurements={})
        self.assertFalse(d.transitioned)
        e = evaluate_step(self.recipe, d.state, now_s=121, measurements={})
        self.assertEqual(e.proposed_action, "wait")
        f = evaluate_step(self.recipe, e.state, now_s=122, measurements={"voltage": 11.99})
        self.assertTrue(f.completed)
        self.assertEqual(f.proposed_action, "off")
        self.assertIsNone(evaluate_step(self.recipe, f.state, now_s=123, measurements={}).proposed_action)

    def test_revision_mismatch_and_missing_measurement_fail_closed(self):
        state = StepState("wrong", 0, 100)
        with self.assertRaises(ValueError):
            evaluate_step(self.recipe, state, now_s=101, measurements={"voltage": 14})
        state = StepState(self.recipe.digest, 0, 100)
        with self.assertRaises(ValueError):
            evaluate_step(self.recipe, state, now_s=101, measurements={})
        with self.assertRaises(ValueError):
            evaluate_step(self.recipe, state, now_s=99, measurements={"voltage": 14})
