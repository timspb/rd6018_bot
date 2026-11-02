from application.execution_intent.models import SafetyContext
import unittest
from types import SimpleNamespace

from application.recipe_session_lifecycle import (
    RecipeSession, RecipeExecutionIdentity, advance_recipe_session, restore_recipe_session,
)
from runtime.charge.programs.recipe_schema import parse_recipe
from runtime.charge.programs.recipe_runner import RunnerState


class FakePort:
    def __init__(self):
        self.calls = []

    async def apply_intent(self, intent, *, identity):
        self.calls.append(("set", intent))
        return SimpleNamespace(accepted=True, verified=True)

    async def disable(self, intent, *, identity, reason):
        self.calls.append(("off", intent))
        return SimpleNamespace(accepted=True, verified=True)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.recipe = parse_recipe({"id": "draft", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1.0},
             "until": {"after_seconds": 10}},
            {"action": "off", "params": {}, "until": {"after_seconds": 3}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        self.identity = RecipeExecutionIdentity("existing-session", "trace")

    async def test_no_unadmitted_execution_and_restore_stays_inactive(self):
        port = FakePort()
        session = RecipeSession(self.recipe, self.identity)
        with self.assertRaises(RuntimeError):
            await advance_recipe_session(session, port=port, now_s=100,
                                         measurements={}, safety_context=SafetyContext(), )
        self.assertEqual(port.calls, [])
        restored = restore_recipe_session(recipe=self.recipe, identity=self.identity,
                                          state=RunnerState())
        self.assertTrue(restored.restored_inactive)

    async def test_admitted_active_session_progresses_with_canonical_port(self):
        port = FakePort()
        session = RecipeSession(self.recipe, self.identity)
        session, receipt = await advance_recipe_session(
            session, port=port, now_s=100, measurements={},
            safety_context=SafetyContext(), persist_state=lambda state: None)
        self.assertTrue(receipt.verified)
        self.assertEqual(port.calls[0][0], "set")
        session, receipt = await advance_recipe_session(
            session, port=port, now_s=110, measurements={},
            safety_context=SafetyContext(), persist_state=lambda state: None)
        self.assertTrue(receipt.output_off)
        self.assertEqual(port.calls[1][0], "off")
        session, receipt = await advance_recipe_session(
            session, port=port, now_s=113, measurements={},
            safety_context=SafetyContext(), persist_state=lambda state: None)
        self.assertTrue(session.state.completed)
        self.assertTrue(receipt.output_off)

    async def test_preflight_blocks_wait_after_live_set(self):
        bad = parse_recipe({"id": "unsafe-order", "version": 1, "steps": [
            {"action": "set", "params": {"voltage_v": 14.7, "current_a": 1},
             "until": {"after_seconds": 2}},
            {"action": "wait", "params": {}, "until": {"after_seconds": 2}},
        ]}, max_voltage_v=15.5, max_current_a=7.2)
        port = FakePort()
        session = RecipeSession(bad, self.identity)
        with self.assertRaises(ValueError):
            await advance_recipe_session(session, port=port, now_s=100,
                                         measurements={}, safety_context=SafetyContext(), )
        self.assertEqual(port.calls, [])

    async def test_write_ahead_failure_prevents_hardware_command(self):
        port = FakePort()
        session = RecipeSession(self.recipe, self.identity)
        def fail_write(_state):
            raise OSError("disk full")
        with self.assertRaises(OSError):
            await advance_recipe_session(
                session, port=port, now_s=100, measurements={},
                 safety_context=SafetyContext(), persist_state=fail_write)
        self.assertEqual(port.calls, [])
