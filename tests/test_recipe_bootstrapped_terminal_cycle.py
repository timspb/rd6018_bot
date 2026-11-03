"""Integrated recipe tick after START has already verified and persisted first SET.

No physical RD6018 access: port records intended operations in memory.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from application.charge_session_tick import run_charge_session_tick
from application.recipe_existing_session import ExistingRecipeBinding
from application.recipe_session_lifecycle import RecipeSession
from application.recipe_execution_adapter import RecipeExecutionIdentity
from application.execution_intent.models import SafetyContext
from runtime.charge.programs.recipe_engine import StepState
from runtime.charge.programs.recipe_runner import RunnerState
from runtime.charge.programs.recipe_runner_store import save_runner, load_runner
from runtime.charge.programs.recipe_schema import parse_recipe
from test_user_recipe_full_cycle import FakePort


class VerifiedStartToTerminalTickTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootstrapped_set_not_replayed_then_terminal_off_verified(self):
        recipe = parse_recipe({
            "id": "cycle", "version": 1, "steps": [
                {"action": "set", "params": {"voltage_v": 13.8, "current_a": 1.2},
                 "until": {"after_seconds": 2}},
                {"action": "off", "params": {}, "until": {"after_seconds": 2}},
            ],
        }, max_voltage_v=15.5, max_current_a=7.2)
        port = FakePort()
        session_id = RecipeExecutionIdentity("already-started", "trace")
        initial = RunnerState(step=StepState(recipe.digest, 0, 100.0))
        session = RecipeSession(recipe, session_id, initial)
        stop = Mock()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "runner.json"
            save_runner(path, recipe, initial)
            binding = ExistingRecipeBinding(session, port, SafetyContext(), 15.5, path)
            host = SimpleNamespace(
                is_active=True, _existing_recipe_execution_binding=binding,
                OVP_OFFSET=0.1, OCP_OFFSET=0.1, _cap_current=lambda x: x,
                stop=stop,
            )
            for at in (101.0, 102.0, 104.0):
                with patch("application.charge_session_tick.time.time", return_value=at):
                    out = await run_charge_session_tick(
                        host, 13.8, 0.1, 25.0, True, 0.0
                    )
                self.assertEqual(out, {})
            self.assertEqual([action[0] for action in port.actions], ["off", "off"])
            self.assertFalse(port.execution_owner.output)
            stop.assert_called_once_with(clear_session=True)
            self.assertIsNone(host._existing_recipe_execution_binding)
            self.assertTrue(load_runner(path, recipe).completed)