import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from application.recipe_session_lifecycle import (
    RecipeSession, RecipeExecutionIdentity, advance_durable_recipe_session,
    restore_durable_recipe_session,
)
from runtime.charge.programs.recipe_runner_store import load_runner
from runtime.charge.programs.recipe_schema import parse_recipe


class InterruptedPort:
    def __init__(self):
        self.calls = 0

    async def apply_intent(self, intent, *, identity):
        self.calls += 1
        raise RuntimeError("connection lost after physical call")


class DurableLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_saved_before_uncertain_hardware_result(self):
        recipe = parse_recipe({"id": "lab", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
             "until": {"after_seconds": 10}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        identity = RecipeExecutionIdentity("s", "t")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "runner.json"
            port = InterruptedPort()
            session = RecipeSession(recipe, identity)
            with self.assertRaises(RuntimeError):
                await advance_durable_recipe_session(
                    session, port=port, now_s=100, measurements={},
                     state_path=path)
            self.assertEqual(port.calls, 1)
            saved = load_runner(path, recipe)
            self.assertIsNotNone(saved.pending)
            restored = restore_durable_recipe_session(
                recipe=recipe, identity=identity, state_path=path)
            self.assertTrue(restored.restored_inactive)
            with self.assertRaises(RuntimeError):
                await advance_durable_recipe_session(
                    restored, port=port, now_s=101, measurements={},
                     state_path=path)
            self.assertEqual(port.calls, 1)
