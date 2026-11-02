import unittest
from types import SimpleNamespace
from application.start_transaction_runner import StartTransactionRunner


class StartTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_recipe_survives_transaction_runner(self):
        seen=[]
        async def owner(app,event,pending):
            seen.append((pending.recipe_id,pending.recipe_version))
            return True
        transaction=SimpleNamespace(
            profile="AGM",capacity_ah=70.0,intent="normal",
            battery_id="battery-test",condition="unknown",
            intent_metadata={"user_recipe_id":"my_mode","user_recipe_version":3},
            trace_id="trace",actor="7",source="telegram",
            correlation_metadata={},
        )
        result=await StartTransactionRunner(app=object(),transaction_owner=owner)(transaction)
        self.assertTrue(result.started)
        self.assertEqual(seen,[("my_mode",3)])

    async def test_plain_start_remains_plain(self):
        seen=[]
        async def owner(app,event,pending):
            seen.append((pending.recipe_id,pending.recipe_version))
            return True
        transaction=SimpleNamespace(
            profile="AGM",capacity_ah=70.0,intent="normal",
            battery_id="battery-test",condition="unknown",
            intent_metadata={},trace_id="trace",actor="7",
            source="telegram",correlation_metadata={},
        )
        result=await StartTransactionRunner(app=object(),transaction_owner=owner)(transaction)
        self.assertTrue(result.started)
        self.assertEqual(seen,[(None,None)])
