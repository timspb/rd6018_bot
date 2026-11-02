import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from application.recipe_existing_session import advance_in_existing_session
from application.recipe_execution_adapter import RecipeExecutionIdentity
from application.recipe_session_lifecycle import RecipeSession
from application.execution_intent.models import SafetyContext
from runtime.charge.programs.recipe_schema import parse_recipe


class FakeOwner:
    def __init__(self):
        self.output = True
    async def get_all_live(self):
        return {"switch": "on" if self.output else "off"}


class FakePort:
    def __init__(self):
        self.execution_owner = FakeOwner()
        self.actions = []
    async def apply_intent(self, intent, **kwargs):
        self.actions.append(("set", intent.requested_voltage_v))
        return SimpleNamespace(accepted=True, verified=True)
    async def disable(self, intent, **kwargs):
        self.execution_owner.output = False
        self.actions.append(("off", 0))
        return SimpleNamespace(accepted=True, verified=True)
    async def enable(self, intent, **kwargs):
        self.execution_owner.output = True
        self.actions.append(("enable", intent.requested_voltage_v))
        return SimpleNamespace(accepted=True, verified=True)


class FullCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_off_wait_set_and_terminal_off(self):
        recipe = parse_recipe({"id":"cycle","version":1,"steps":[
            {"action":"set","params":{"voltage_v":14.6,"current_a":1.0},"until":{"after_seconds":2}},
            {"action":"off","params":{},"until":{"after_seconds":2}},
            {"action":"wait","params":{},"until":{"after_seconds":2}},
            {"action":"set","params":{"voltage_v":14.7,"current_a":1.0},"until":{"after_seconds":2}},
        ]},max_voltage_v=15.5,max_current_a=7.2)
        session = RecipeSession(recipe,RecipeExecutionIdentity("test-session","trace"))
        port=FakePort()
        host=SimpleNamespace(OVP_OFFSET=.1,OCP_OFFSET=.1,_cap_current=lambda x:x)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"state.json"
            for time_s in (0,2,4,6,8):
                session,receipt=await advance_in_existing_session(
                    session,host=host,port=port,now_s=time_s,
                    measurements={"voltage":14.7,"current":.1},
                    safety_context=SafetyContext(),voltage_ceiling_v=15.5,
                    state_path=path)
                self.assertTrue(receipt.verified)
            self.assertTrue(session.state.completed)
            self.assertEqual([a[0] for a in port.actions],
                             ["set","off","enable","off"])
            self.assertFalse(port.execution_owner.output)
            session,receipt=await advance_in_existing_session(
                session,host=host,port=port,now_s=9,measurements={},
                safety_context=SafetyContext(),voltage_ceiling_v=15.5,
                state_path=path)
            self.assertIsNone(receipt)
            self.assertEqual(len(port.actions),4)
