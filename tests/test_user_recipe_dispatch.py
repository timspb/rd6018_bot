import unittest

from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_engine import evaluate_step
from runtime.charge.programs.recipe_dispatch import (
    ActionReceipt, propose_action, acknowledge_action, may_auto_resume_from_checkpoint,
)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.recipe = parse_recipe({"id": "trial", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 2.0},
             "until": {"after_seconds": 5}},
            {"action": "off", "params": {}, "until": {"after_seconds": 2}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)

    def test_set_requires_matched_verified_receipt(self):
        decision = evaluate_step(self.recipe, None, now_s=20, measurements={})
        pending = propose_action(self.recipe, decision)
        self.assertEqual(pending, propose_action(self.recipe, decision))
        self.assertFalse(acknowledge_action(pending, ActionReceipt(
            pending.action_id, True, False, False)))
        with self.assertRaises(ValueError):
            acknowledge_action(pending, ActionReceipt("wrong", True, True, False))
        self.assertTrue(acknowledge_action(pending, ActionReceipt(
            pending.action_id, True, True, False)))

    def test_off_requires_off_readback(self):
        first = evaluate_step(self.recipe, None, now_s=20, measurements={})
        second = evaluate_step(self.recipe, first.state, now_s=25, measurements={})
        pending = propose_action(self.recipe, second)
        self.assertEqual(pending.operation, "off")
        self.assertFalse(acknowledge_action(pending, ActionReceipt(
            pending.action_id, True, True, False)))
        self.assertTrue(acknowledge_action(pending, ActionReceipt(
            pending.action_id, True, True, True)))

    def test_no_unattended_automatic_resume(self):
        self.assertFalse(may_auto_resume_from_checkpoint(output_confirmed_off=True))
        self.assertFalse(may_auto_resume_from_checkpoint(output_confirmed_off=False))
