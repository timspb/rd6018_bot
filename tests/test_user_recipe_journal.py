import tempfile
import unittest
from pathlib import Path
from application.recipe_session_lifecycle import (
    RecipeSession, RecipeExecutionIdentity, advance_durable_recipe_session,
)
from runtime.charge.programs.recipe_journal import read_events
from runtime.charge.programs.recipe_schema import parse_recipe


class InterruptedPort:
    async def apply_intent(self, intent, *, identity):
        raise RuntimeError("link interrupted")


class JournalTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_and_interrupted_recorded_with_identity(self):
        recipe = parse_recipe({"id": "lab", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
             "until": {"after_seconds": 5}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        with tempfile.TemporaryDirectory() as folder:
            journal = Path(folder) / "events.jsonl"
            state = Path(folder) / "runner.json"
            session = RecipeSession(recipe, RecipeExecutionIdentity("s", "t"),
                                    admission_epoch="epoch")
            with self.assertRaises(RuntimeError):
                await advance_durable_recipe_session(
                    session, port=InterruptedPort(), now_s=100, measurements={},
                    admitted_epoch="epoch", state_path=state, journal_path=journal)
            events = read_events(journal)
            self.assertEqual([x["event"] for x in events], ["PENDING", "INTERRUPTED"])
            self.assertEqual(events[0]["action_id"], events[1]["action_id"])
            self.assertEqual(events[0]["digest"], recipe.digest)
