"""Zero OVP/OCP commands: firmware-specific disable is OFF-only and readback-bound."""
from __future__ import annotations
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from runtime.safety.runtime_guard import RuntimeSafetyGuard, RuntimeSafetyError


class Backend:
    def __init__(self, status="off", *, age_s=1.0, code=None):
        self.commands=[]
        self.live={"switch":status, "ovp":16.6,"ocp":1.32}
        stamp=(datetime.now(timezone.utc)-timedelta(seconds=age_s)).isoformat()
        self.live["_meta"]={"switch":{"last_reported":stamp}}
        if code is not None:
            self.live["output_state_code_v2"]=code
            self.live["_meta"]["output_state_code_v2"]={"last_reported":stamp}

    async def get_all_live(self):
        return self.live.copy()
    async def set_ovp(self, v):
        self.commands.append(("ovp",v));self.live["ovp"]=v;return True
    async def set_ocp(self, v):
        self.commands.append(("ocp",v));self.live["ocp"]=v;return True
    async def turn_off(self, entity_id=None):
        self.live["switch"]="off";return True
    async def turn_on(self, entity_id=None):
        self.live["switch"]="on";return True
    async def set_voltage(self, v):
        self.commands.append(("voltage",v));return True
    async def set_current(self, v):
        self.commands.append(("current",v));return True


class TestZeroProtectionGate(unittest.IsolatedAsyncioTestCase):
    def make(self, backend):
        guard = RuntimeSafetyGuard(SimpleNamespace(
            hass=backend,charge_controller=SimpleNamespace(is_active=False),
            _charge_notify=lambda *a,**kw:None))
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        return guard

    async def test_zero_allowed_only_when_fresh_off(self):
        backend=Backend()
        guard=self.make(backend)
        self.assertTrue(await guard.set_ovp(0.0))
        self.assertTrue(await guard.set_ocp(0.0))
        self.assertEqual(backend.commands,[("ovp",0.0),("ocp",0.0)])

    async def test_zero_rejected_when_on(self):
        backend=Backend("on")
        guard=self.make(backend)
        with self.assertRaises(RuntimeSafetyError):
            await guard.set_ovp(0.0)
        # A failed active write starts the existing emergency OFF path.
        self.assertEqual(backend.commands,[])

    async def test_zero_rejected_when_unknown_or_stale(self):
        for status,age in (("unknown",1),("off",301)):
            with self.subTest(status=status,age=age):
                backend=Backend(status,age_s=age)
                guard=self.make(backend)
                self.assertFalse(await guard.set_ovp(0.0))
                self.assertFalse(await guard.set_ocp(0.0))
                self.assertEqual(backend.commands,[])

    async def test_v2_on_cannot_be_bypassed_by_switch_off(self):
        backend=Backend("off",code=1)
        guard=self.make(backend)
        self.assertFalse(await guard.set_ovp(0.0))
        self.assertFalse(await guard.set_ocp(0.0))
        self.assertEqual(backend.commands,[])

    async def test_negative_not_allowed_even_when_off(self):
        backend=Backend()
        guard=self.make(backend)
        self.assertFalse(await guard.set_ovp(-0.1))
        self.assertFalse(await guard.set_ocp(-0.1))
        self.assertEqual(backend.commands,[])


if __name__=="__main__":
    unittest.main()
