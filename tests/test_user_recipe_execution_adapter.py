from application.execution_intent.models import SafetyContext
import asyncio
import unittest
from types import SimpleNamespace

from application.recipe_execution_adapter import execute_recipe_action, RecipeExecutionIdentity
from runtime.charge.programs.recipe_dispatch import PendingAction


class FakePort:
    def __init__(self):
        self.calls = []

    async def apply_intent(self, intent, *, identity):
        self.calls.append(("set", intent, identity))
        return SimpleNamespace(accepted=True, verified=True)

    async def disable(self, intent, *, identity, reason):
        self.calls.append(("off", intent, identity))
        return SimpleNamespace(accepted=True, verified=True)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_session_admission(self):
        port = FakePort()
        pending = PendingAction("digest", 0, "id-set", "set",
                                {"voltage_v": 14.7, "current_a": 2})
        with self.assertRaises(ValueError):
            await execute_recipe_action(port=port, pending=pending,
                                        identity=RecipeExecutionIdentity("", "t"), safety_context=SafetyContext())
        self.assertEqual(port.calls, [])

    async def test_uses_existing_port_and_correlated_receipt(self):
        port = FakePort()
        identity = RecipeExecutionIdentity("s", "t")
        pending = PendingAction("digest", 0, "id-set", "set",
                                {"voltage_v": 14.7, "current_a": 2})
        receipt = await execute_recipe_action(port=port, pending=pending,
                                              identity=identity, safety_context=SafetyContext())
        self.assertTrue(receipt.verified)
        self.assertEqual(port.calls[0][1].source_decision_id, "id-set")
        off = PendingAction("digest", 1, "id-off", "off", {})
        receipt = await execute_recipe_action(port=port, pending=off,
                                              identity=identity, safety_context=SafetyContext())
        self.assertTrue(receipt.output_off)
        self.assertEqual(port.calls[1][0], "off")
