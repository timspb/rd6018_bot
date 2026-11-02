import unittest

from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_runner import RunnerState, tick, confirm
from runtime.charge.programs.recipe_dispatch import ActionReceipt


class RunnerTests(unittest.TestCase):
    def test_hardware_ack_gates_step_and_timer(self):
        recipe = parse_recipe({"id": "run", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 2},
             "until": {"after_seconds": 10}},
            {"action": "off", "params": {}, "until": {"after_seconds": 5}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        first = tick(recipe, RunnerState(), now_s=100, measurements={})
        self.assertEqual(first.command.operation, "set")
        stalled = tick(recipe, first.state, now_s=999, measurements={})
        self.assertEqual(stalled.command.action_id, first.command.action_id)
        self.assertEqual(stalled.state.step.step_index, 0)
        fail = ActionReceipt(first.command.action_id, True, False, False)
        self.assertEqual(confirm(first.state, fail, confirmed_at_s=110), first.state)
        ack = ActionReceipt(first.command.action_id, True, True, False)
        state = confirm(first.state, ack, confirmed_at_s=110)
        self.assertFalse(tick(recipe, state, now_s=119, measurements={}).blocked)
        second = tick(recipe, state, now_s=120, measurements={})
        self.assertEqual(second.command.operation, "off")
        self.assertFalse(confirm(second.state, ActionReceipt(
            second.command.action_id, True, True, False),
            confirmed_at_s=121).completed)
        verified = confirm(second.state, ActionReceipt(
            second.command.action_id, True, True, True), confirmed_at_s=121)
        self.assertFalse(verified.completed)
        ending = tick(recipe, verified, now_s=126, measurements={})
        self.assertEqual(ending.command.operation, "off")
        self.assertTrue(ending.state.terminal_pending)
        finished = confirm(ending.state, ActionReceipt(
            ending.command.action_id, True, True, True), confirmed_at_s=127)
        self.assertTrue(finished.completed)
        self.assertIsNone(tick(recipe, finished, now_s=200, measurements={}).command)
