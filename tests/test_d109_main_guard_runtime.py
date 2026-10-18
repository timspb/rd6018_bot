"""D109 real runtime composition simulation + strict ESP Native lease provenance."""
from __future__ import annotations
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch
import time
import unittest

from application.main_guard_runtime import execute_due_main_guard
from edge_safety_lease import EdgeLeaseState, EdgeSafetyLease, EdgeSafetyLeaseError
from runtime.charge.strategy.main_guard_admission import admit_main_guard_shadow
from runtime.charge.strategy.main_guard_shadow import MainGuardShadow
from tests.test_d109_main_guard_checkpoint import D109CanonicalGuardIntegration
import json


class PositiveLease:
    renewals_suspended=False
    def __init__(self, *, armed=True, remaining=850.0, native=True, modbus_age=2.0):
        self.armed=armed
        self.remaining=remaining
        self.native=native
        self.modbus_age=modbus_age
    async def read_state(self, *, require_native=False):
        if require_native and not self.native:
            raise EdgeSafetyLeaseError("not-native")
        return EdgeLeaseState(self.armed,False,False,1,self.modbus_age,self.remaining)


class D109RuntimeBridgeTests(D109CanonicalGuardIntegration):
    def setup_app(self, lease=None):
        lease=lease or PositiveLease()
        self.app=SimpleNamespace(
            charge_controller=self.host,
            runtime_safety_guard=SimpleNamespace(
                edge_lease_enforced=True,edge_safety_lease=lease,
            ),
            rd_control_mode_manager=SimpleNamespace(hands_off=False),
        )
        self.shadow=MainGuardShadow(guard=self.guard)

    async def run_runtime(self):
        doc=json.loads(self.path.read_text())
        admission=admit_main_guard_shadow(
            controller=self.host,session_document=doc,
            live=await self.owner.get_all_live(),now_epoch_s=time.time())
        self.assertIsNotNone(admission)
        guard,proposal=self.proposal(self.guard,0)
        self.shadow.guard=guard
        self.shadow.proposal=proposal
        self.assertIsNotNone(proposal)
        with patch("application.main_guard_runtime.time.monotonic",return_value=1801.0):
            async with self.lock:
                return await execute_due_main_guard(
                    app=self.app,port=self.port,admission=admission,
                    shadow=self.shadow,proposal=proposal,
                    session_path=str(self.path),
                )

    async def test_native_lease_positive_changes_current_and_persists(self):
        self.setup_app()
        result=await self.run_runtime()
        self.assertTrue(result.verified,result.reason)
        self.assertEqual(self.shadow.guard.hardware_limit_a,5.0)
        self.assertIsNone(self.shadow.proposal)
        self.assertEqual(self.host._device_set_current,5.0)
        self.assertEqual(self.host._phase_current_limit,5.0)
        self.assertEqual(json.loads(self.path.read_text())["target_current"],5.0)

    async def test_lease_unknown_or_low_remaining_makes_no_write(self):
        for lease in (PositiveLease(native=False),PositiveLease(armed=False),
                      PositiveLease(remaining=30),PositiveLease(modbus_age=30)):
            with self.subTest(lease=lease.__dict__):
                self.setup_app(lease)
                self.owner.events.clear()
                result=await self.run_runtime()
                self.assertIsNone(result)
                self.assertEqual(self.owner.events,[])
                self.assertNotIn("main_current_guard_v1",json.loads(self.path.read_text()))

    async def test_hands_off_does_not_use_guard_actuator(self):
        self.setup_app()
        self.app.rd_control_mode_manager.hands_off=True
        self.assertIsNone(await self.run_runtime())
        self.assertEqual(self.owner.events,[])

    async def test_hardware_ack_uncertain_quarantines_existing_port(self):
        self.setup_app()
        self.owner.mirror=False
        result=await self.run_runtime()
        self.assertFalse(result.verified)
        self.assertTrue(result.hardware_write_invoked)
        self.assertTrue(self.port.session_recovery_guard.quarantined)
        self.assertIn(("OFF",),self.owner.events)

    async def test_lease_disabled_must_not_authorize_current_change(self):
        self.setup_app()
        self.app.runtime_safety_guard.edge_lease_enforced=False
        self.assertIsNone(await self.run_runtime())
        self.assertEqual(self.owner.events,[])


class FakeHassStates:
    def __init__(self,native=True):
        self.native=native
        self.states={}
    async def get_state(self,entity):
        key=entity.rsplit("_",1)[-1]
        if entity.endswith("lease_armed"):val="on"
        elif entity.endswith("lease_tripped"):val="off"
        elif entity.endswith("boot_quarantine"):val="off"
        elif entity.endswith("lease_generation"):val=12
        elif entity.endswith("modbus_age"):val=2.0
        elif entity.endswith("lease_remaining"):val=850.0
        else:raise AssertionError(entity)
        binary=entity.startswith("binary_sensor.")
        attrs={"source":"esp_native_api" if self.native else "ha_rest",
               "native_type":"BinarySensorState" if binary else "SensorState",
               "age_s":0.2}
        return val,attrs


class D109NativeLeaseProvenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_source_only_is_accepted_for_guard(self):
        native=EdgeSafetyLease(FakeHassStates(native=True))
        state=await native.read_state(require_native=True)
        self.assertTrue(state.armed)
        self.assertEqual(state.remaining_s,850.0)
        ha=EdgeSafetyLease(FakeHassStates(native=False))
        with self.assertRaisesRegex(EdgeSafetyLeaseError,"direct native"):
            await ha.read_state(require_native=True)
        self.assertTrue((await ha.read_state()).armed)

if __name__=="__main__":
    unittest.main()
