import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from application.execution_intent.models import SafetyContext
from application.recipe_existing_session import advance_in_existing_session
from application.recipe_session_lifecycle import RecipeSession
from application.recipe_execution_adapter import RecipeExecutionIdentity
from runtime.charge.programs.recipe_schema import parse_recipe


class ExistingRecipeVILimitsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        recipe = parse_recipe({
            "id": "sample", "version": 1,
            "steps": [{"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
                       "until": {"after_seconds": 60}}],
        }, max_voltage_v=15.5, max_current_a=7.2)
        self.session = RecipeSession(recipe, RecipeExecutionIdentity("session", "trace"))
        self.host = SimpleNamespace(_cap_current=lambda value: min(value, 7.2))

    async def test_recipe_uses_active_voltage_envelope_and_current_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("application.recipe_existing_session.advance_durable_recipe_session",
                       new_callable=AsyncMock, return_value=(self.session, None)) as advance:
                await advance_in_existing_session(
                    self.session, host=self.host, port=object(), now_s=1,
                    measurements={}, safety_context=SafetyContext(),
                    voltage_ceiling_v=15.5, state_path=Path(tmp) / "runner.json",
                )
                self.assertEqual(15.5, advance.await_args.kwargs["recipe_voltage_ceiling_v"])

    async def test_voltage_envelope_violation_never_calls_session_owner(self):
        with patch("application.recipe_existing_session.advance_durable_recipe_session",
                   new_callable=AsyncMock) as advance:
            with self.assertRaises(ValueError):
                await advance_in_existing_session(
                    self.session, host=self.host, port=object(), now_s=1,
                    measurements={}, safety_context=SafetyContext(),
                    voltage_ceiling_v=14.0, state_path="unused",
                )
            advance.assert_not_awaited()

    async def test_current_cap_violation_never_calls_session_owner(self):
        self.host._cap_current = lambda value: 0.5
        with patch("application.recipe_existing_session.advance_durable_recipe_session",
                   new_callable=AsyncMock) as advance:
            with self.assertRaises(ValueError):
                await advance_in_existing_session(
                    self.session, host=self.host, port=object(), now_s=1,
                    measurements={}, safety_context=SafetyContext(),
                    voltage_ceiling_v=15.5, state_path="unused",
                )
            advance.assert_not_awaited()
