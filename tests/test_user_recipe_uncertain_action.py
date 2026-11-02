import tempfile
import unittest
from pathlib import Path
from application.execution_intent.models import SafetyContext
from application.recipe_session_lifecycle import RecipeSession, advance_durable_recipe_session
from application.recipe_execution_adapter import RecipeExecutionIdentity
from runtime.charge.programs.recipe_runner_store import load_runner
from runtime.charge.programs.recipe_schema import parse_recipe


class FailedPort:
    def __init__(self):
        self.calls = 0
    async def apply_intent(self, intent, *, identity):
        self.calls += 1
        raise ConnectionError("uncertain hardware acknowledgement")


class UncertainActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_set_not_resent_on_next_tick(self):
        recipe = parse_recipe({"id": "uncertain", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
             "until": {"after_seconds": 2}}
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        port = FailedPort()
        session = RecipeSession(recipe, RecipeExecutionIdentity("session", "trace"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.json"
            kwargs = dict(port=port, measurements={}, safety_context=SafetyContext(),
                          state_path=path)
            with self.assertRaises(ConnectionError):
                await advance_durable_recipe_session(session, now_s=0, **kwargs)
            stored = load_runner(path, recipe)
            self.assertIsNotNone(stored.pending)
            with self.assertRaises(RuntimeError):
                await advance_durable_recipe_session(session, now_s=1, **kwargs)
            self.assertEqual(port.calls, 1)
