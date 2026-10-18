"""Reproduce STOP/disarm preempting in-flight START/arm on fake edge only."""
import asyncio
import unittest
from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig, EdgeSafetyLeaseError
from tests.test_edge_safety_lease import FakeHass


class PausedRenewHass(FakeHass):
    def __init__(self):
        super().__init__()
        self.renew_started = asyncio.Event()
        self.renew_resume = asyncio.Event()

    async def press_button(self, entity_id):
        if entity_id.endswith("safety_lease_renew"):
            self.renew_started.set()
            await self.renew_resume.wait()
        return await super().press_button(entity_id)


class PausedPreflightHass(FakeHass):
    def __init__(self):
        super().__init__()
        self.read_started = asyncio.Event()
        self.read_resume = asyncio.Event()
        self.pause_first_read = True

    async def get_state(self, entity_id):
        if self.pause_first_read:
            self.pause_first_read = False
            self.read_started.set()
            await self.read_resume.wait()
        return await super().get_state(entity_id)


class ConcurrentStopArmTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_before_native_preflight_finishes_never_sends_renew(self):
        hass = PausedPreflightHass()
        lease = EdgeSafetyLease(hass, EdgeSafetyLeaseConfig(
            ack_attempts=1, ack_delay_s=0,
            disarm_ack_attempts=1, disarm_ack_delay_s=0))
        arm_task = asyncio.create_task(lease.arm())
        await asyncio.wait_for(hass.read_started.wait(), timeout=2)
        stop_task = asyncio.create_task(lease.disarm())
        await asyncio.sleep(0)
        self.assertTrue(lease.renewals_suspended)
        hass.read_resume.set()
        try:
            with self.assertRaisesRegex(EdgeSafetyLeaseError, "suspended"):
                await arm_task
            self.assertTrue(await stop_task)
            self.assertNotIn(lease.config.renew_entity, hass.presses)
            self.assertFalse((await lease.read_state()).armed)
        finally:
            hass.read_resume.set()
            await asyncio.gather(arm_task, stop_task, return_exceptions=True)

    async def test_stop_preempts_inflight_start_arm(self):
        hass = PausedRenewHass()
        lease = EdgeSafetyLease(hass, EdgeSafetyLeaseConfig(
            ack_attempts=1, ack_delay_s=0,
            disarm_ack_attempts=1, disarm_ack_delay_s=0))
        arm_task = asyncio.create_task(lease.arm())
        await asyncio.wait_for(hass.renew_started.wait(), timeout=2)
        self.assertFalse(lease.renewals_suspended)
        stop_task = asyncio.create_task(lease.disarm())
        await asyncio.sleep(0)
        self.assertTrue(lease.renewals_suspended)
        hass.renew_resume.set()
        try:
            with self.assertRaisesRegex(EdgeSafetyLeaseError, "suspended"):
                await arm_task
            self.assertTrue(await stop_task)
            self.assertTrue(lease.renewals_suspended)
            self.assertFalse((await lease.read_state()).armed)
        finally:
            hass.renew_resume.set()
            await asyncio.gather(arm_task,stop_task, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
