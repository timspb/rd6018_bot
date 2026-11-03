"""Selection metadata survives the existing START router's single owner."""
import types
import unittest
from unittest.mock import AsyncMock

from pb_domain import BatteryCondition, ChargeIntent
from application.start_transaction_adapter import StartTransactionInput
from application.start_transaction_runner import StartTransactionRunner


class NativeSelectionStartMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_selection_is_forwarded_to_exactly_one_start_owner(self):
        received = []
        async def owner(app, event, pending):
            received.append(pending)
            return False
        tx = StartTransactionInput(
            trace_id="trace", profile="EFB", chemistry="efb",
            capacity_ah=72., battery_id="battery-1",
            recipe_id="canonical-efb", target_voltage_v=14.8,
            target_current_a=7.2, ownership_decision="available",
            safety_decision="allowed",
            intent=ChargeIntent.NORMAL,
            condition=BatteryCondition.UNKNOWN,
            actor="7", source="telegram",
            intent_metadata={"native_recipe_name": "my_efb",
                             "native_recipe_version": 2},
        )
        app = types.SimpleNamespace()
        result = await StartTransactionRunner(
            app, transaction_owner=owner)(tx)
        self.assertFalse(result.started)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].native_recipe_name, "my_efb")
        self.assertEqual(received[0].native_recipe_version, 2)
        self.assertIsNone(received[0].recipe_id)

    async def test_user_step_and_default_start_remain_separate(self):
        received = []
        async def owner(app, event, pending):
            received.append(pending)
            return False
        tx = StartTransactionInput(
            trace_id="trace", profile="EFB", chemistry="efb",
            capacity_ah=72., battery_id="battery-1",
            recipe_id="canonical-efb", target_voltage_v=14.8,
            target_current_a=7.2, ownership_decision="available",
            safety_decision="allowed",
            intent=ChargeIntent.NORMAL,
            condition=BatteryCondition.UNKNOWN,
            actor="7", source="telegram",
            intent_metadata={"user_recipe_id": "step_recipe",
                             "user_recipe_version": 1},
        )
        await StartTransactionRunner(
            types.SimpleNamespace(), transaction_owner=owner)(tx)
        self.assertEqual(received[0].recipe_id, "step_recipe")
        self.assertIsNone(received[0].native_recipe_name)
