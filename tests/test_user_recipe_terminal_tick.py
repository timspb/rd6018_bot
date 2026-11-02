import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from application.charge_session_tick import run_charge_session_tick
from application.recipe_existing_session import ExistingRecipeBinding
from application.recipe_session_lifecycle import RecipeSession
from application.recipe_execution_adapter import RecipeExecutionIdentity
from application.execution_intent.models import SafetyContext
from runtime.charge.programs.recipe_runner import RunnerState
from runtime.charge.programs.recipe_schema import parse_recipe


class RecipeTerminalTickTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_ack_uses_normal_stop_and_clears_binding(self):
        recipe = parse_recipe({"id":"test","version":1,"steps":[
            {"action":"off","params":{},"until":{"after_seconds":1}}
        ]},max_voltage_v=15.5,max_current_a=7.2)
        session=RecipeSession(recipe,RecipeExecutionIdentity("session","trace"))
        binding=ExistingRecipeBinding(session,object(),SafetyContext(),15.5,"state.json")
        host=SimpleNamespace(is_active=True,stop=Mock(),_existing_recipe_execution_binding=binding)
        completed=RecipeSession(recipe,session.identity,RunnerState(completed=True))
        with patch("application.recipe_existing_session.advance_in_existing_session",
                   new_callable=AsyncMock,return_value=(completed,SimpleNamespace(verified=True))):
            await run_charge_session_tick(host,14.7,0.1,25.0,True,0.0)
        host.stop.assert_called_once_with(clear_session=True)
        self.assertIsNone(host._existing_recipe_execution_binding)

    async def test_unfinished_does_not_stop(self):
        recipe = parse_recipe({"id":"test","version":1,"steps":[
            {"action":"off","params":{},"until":{"after_seconds":1}}
        ]},max_voltage_v=15.5,max_current_a=7.2)
        session=RecipeSession(recipe,RecipeExecutionIdentity("session","trace"))
        binding=ExistingRecipeBinding(session,object(),SafetyContext(),15.5,"state.json")
        host=SimpleNamespace(is_active=True,stop=Mock(),_existing_recipe_execution_binding=binding)
        with patch("application.recipe_existing_session.advance_in_existing_session",
                   new_callable=AsyncMock,return_value=(session,None)):
            await run_charge_session_tick(host,14.7,0.1,25.0,True,0.0)
        host.stop.assert_not_called()
        self.assertIs(host._existing_recipe_execution_binding,binding)
