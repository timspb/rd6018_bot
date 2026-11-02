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
from runtime.charge.programs.recipe_runner import RunnerState


class ExistingSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        recipe = parse_recipe({
            "id": "sample", "version": 1,
            "steps": [{"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
                       "until": {"after_seconds": 60}}],
        }, max_voltage_v=15.5, max_current_a=7.2)
        self.session = RecipeSession(recipe, RecipeExecutionIdentity("session", "trace"))
        self.host = SimpleNamespace(OVP_OFFSET=0.1, OCP_OFFSET=0.1,
                                    _cap_current=lambda x: min(x, 7.2))

    async def test_start_offsets_passed_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("application.recipe_existing_session.advance_durable_recipe_session",
                       new_callable=AsyncMock, return_value=(self.session, None)) as advance:
                await advance_in_existing_session(
                    self.session, host=self.host, port=object(), now_s=1,
                    measurements={}, safety_context=SafetyContext(),
                    voltage_ceiling_v=15.5, state_path=Path(tmp)/"runner.json",
                )
                limits = advance.await_args.kwargs["restart_limits"]
                self.assertAlmostEqual(limits[0], 14.8)
                self.assertAlmostEqual(limits[1], 1.1)
                self.assertEqual(limits[2], 15.5)

    async def test_envelope_violation_never_calls_port(self):
        with patch("application.recipe_existing_session.advance_durable_recipe_session",
                   new_callable=AsyncMock) as advance:
            with self.assertRaises(ValueError):
                await advance_in_existing_session(
                    self.session, host=self.host, port=object(), now_s=1,
                    measurements={}, safety_context=SafetyContext(),
                    voltage_ceiling_v=14.0, state_path="unused",
                )
            advance.assert_not_awaited()

    async def test_restored_session_does_not_advance(self):
        restored = RecipeSession(self.session.recipe, self.session.identity,
                                 RunnerState(), restored_inactive=True)
        with patch("application.recipe_existing_session.advance_durable_recipe_session",
                   new_callable=AsyncMock) as advance:
            with self.assertRaises(RuntimeError):
                await advance_in_existing_session(
                    restored, host=self.host, port=object(), now_s=1,
                    measurements={}, safety_context=SafetyContext(),
                    voltage_ceiling_v=15.5, state_path="unused",
                )
            advance.assert_not_awaited()
