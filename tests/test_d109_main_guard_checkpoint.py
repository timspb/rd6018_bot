"""D109 source-only full charge controller + canonical file + existing port test."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import unittest

from charge_controller import ManagedChargeController
from application.execution_port import ExecutionPort
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from application.main_guard_transaction import MainGuardAuthority
from application.main_guard_checkpoint import (
    CanonicalMainGuardCheckpoint, MainGuardCheckpointError,
)
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import GUARD_KEY, read_guard
from runtime.charge.strategy.main_guard_admission import admit_main_guard_shadow
from tests.test_main_guard_transaction import FakeOwner
import charge_controller


class D109CanonicalGuardIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="d109-main-")
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"charge_session.json"
        self.host=ManagedChargeController(None,battery_id="battery-real")
        self.epoch=time.time()
        self.host.battery_type="EFB"
        self.host.ah_capacity=70
        self.host.current_stage=self.host.STAGE_MAIN
        self.host.stage_start_time=self.epoch-500
        self.host.total_start_time=self.epoch-1000
        self.host._v2_trace_session_id="a"*32
        self.host._v2_trace_started_at=self.epoch-1000
        self.host._v2_battery_id="battery-real"
        with patch.object(charge_controller,"SESSION_FILE",str(self.path)):
            self.host._save_session(14.4,4.0,10.0)
        self.owner=FakeOwner()
        self.owner.live["set_current_readback_v2"]=7.0
        self.owner.live["ocp_readback_v2"]=7.1
        self.port=ExecutionPort(self.owner)
        self.lock=GuardExecutionOwnerLock()
        self.port.bind_guard_owner_lock(self.lock)
        self.writer=CanonicalMainGuardCheckpoint(
            controller=self.host, owner_lock=self.lock, path=self.path,
            monotonic_now=lambda:1801.0,
        )
        self.guard=MainCurrentGuard.start(
            session_id="a"*32,battery_id="battery-real",segment_id="main-1",
            capacity_ah=70,recipe_initial_current_a=7,now_s=0
        )

    async def transact(self,guard,proposal,clock=1801.0):
        result=await self.port.execute_main_current_guard_reduction(
            guard=guard,proposal=proposal,persist=self.writer.persist,
            execution_lock=self.lock,now=lambda:clock,max_stage_current_a=12,
            ocp_offset_a=.1,stabilize_delay_s=0.0,
            authority=MainGuardAuthority(
                session_id="a"*32,battery_id="battery-real",
                segment_id=guard.segment_id,profile="EFB",stage="Main Charge",
                lease_armed=True,owner_authorized=True))
        return result

    def proposal(self,guard,_,measured=4):
        proposal=None
        for t in range(int(guard.last_observed_at_s or 0),int(guard.last_observed_at_s or 0)+1801,30):
            guard,proposal=guard.observe(now_s=float(t),output_on=True,
                measured_current_a=measured,fresh=True)
        return guard,proposal

    async def test_first_and_second_reduction_persist_as_one_charge_session(self):
        guard,pending=self.proposal(self.guard,0)
        self.assertIsNotNone(pending)
        result=await self.transact(guard,pending)
        self.assertTrue(result.verified,result.reason)
        self.assertEqual(result.guard.hardware_limit_a,5)
        self.assertEqual(self.owner.events,[("set_current",5.0),("set_ocp",5.1)])
        doc=json.loads(self.path.read_text())
        self.assertEqual(doc["target_current"],5.0)
        self.assertEqual(doc[GUARD_KEY]["revision"],2)
        self.assertEqual(doc["v2_trace_session_id"],"a"*32)
        self.assertEqual(doc["v2_battery_id"],"battery-real")
        self.assertEqual(self.host._main_current_guard.hardware_limit_a,5.0)
        self.assertEqual(self.host._main_target()[1],5.0)
        admitted=admit_main_guard_shadow(
            controller=self.host,session_document=doc,
            live=await self.owner.get_all_live(),now_epoch_s=time.time())
        self.assertIsNotNone(admitted,"D109 must allow NEXT interval after ratchet")
        self.assertEqual(admitted.recipe_initial_current_a,7.0)
        # Guard continues with a lower physical cap; another accepted 30m.
        guard,pending=self.proposal(result.guard,0,measured=2)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.target_limit_a,3)
        self.writer.monotonic_now=lambda:3601.0
        result2=await self.transact(guard,pending,clock=3601.0)
        self.assertTrue(result2.verified,result2.reason)
        self.assertEqual(result2.guard.hardware_limit_a,3.0)
        doc=json.loads(self.path.read_text())
        self.assertEqual(doc["target_current"],3.0)
        self.assertEqual(doc[GUARD_KEY]["revision"],4)
        self.assertEqual(self.host._main_target()[1],3.0)
        # The normal legacy periodic writer must keep, not erase or enlarge,
        # this accepted lower limit on its next canonical session update.
        with patch.object(charge_controller,"SESSION_FILE",str(self.path)):
            self.host._save_session(14.4,2.0,11.0)
        periodic=json.loads(self.path.read_text())
        self.assertEqual(periodic["target_current"],3.0)
        self.assertEqual(periodic[GUARD_KEY]["revision"],5)
        self.assertEqual(self.owner.events,[
            ("set_current",5.0),("set_ocp",5.1),
            ("set_current",3.0),("set_ocp",3.1),
        ])

    async def test_writer_refuses_use_outside_common_owner(self):
        with self.assertRaisesRegex(MainGuardCheckpointError,"owner_lock_required"):
            await self.writer.persist(self.guard.snapshot())
        self.assertNotIn(GUARD_KEY,json.loads(self.path.read_text()))

    async def test_wrong_session_and_missing_file_never_write_hardware(self):
        guard,proposal=self.proposal(self.guard,0)
        previous=self.path.read_bytes()
        self.host._v2_battery_id="battery-other"
        result=await self.transact(guard,proposal)
        self.assertFalse(result.verified)
        self.assertFalse(result.off_confirmed)
        self.assertEqual(self.owner.events,[])
        self.assertEqual(self.path.read_bytes(),previous)

    async def test_atomically_rejected_pending_does_not_touch_device(self):
        guard,proposal=self.proposal(self.guard,0)
        original=self.path.read_bytes()
        with patch("application.main_guard_checkpoint.atomic_session_write",
                   side_effect=OSError("synthetic fsync failure")):
            result=await self.transact(guard,proposal)
        self.assertFalse(result.verified)
        self.assertEqual(self.owner.events,[])
        self.assertEqual(self.path.read_bytes(),original)

    async def test_post_hardware_ack_durable_failure_requests_off(self):
        guard,proposal=self.proposal(self.guard,0)
        original_persist=self.writer.persist
        writes=0
        async def interrupted(snapshot):
            nonlocal writes
            writes+=1
            if writes==2:raise OSError("synthetic post-ACK fsync failure")
            await original_persist(snapshot)
        self.writer.persist=interrupted
        result=await self.transact(guard,proposal)
        self.assertFalse(result.verified)
        self.assertTrue(result.off_confirmed)
        self.assertIn(("OFF",),self.owner.events)
        saved=json.loads(self.path.read_text())
        self.assertEqual(saved["target_current"],7)
        self.assertIsNotNone(saved[GUARD_KEY]["snapshot"]["pending"])

    def test_agm_baseline_remains_unchanged(self):
        self.host.battery_type="AGM"
        self.host._main_current_guard=None
        self.assertEqual(self.host._main_target()[1],7)

if __name__=="__main__":unittest.main()
