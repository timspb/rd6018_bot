"""Regression: normal managed START after verified STOP must explicitly arm ESP lease.

Reuses real lease and managed-runtime safety guard classes with test-only fake
physical I/O. No hardware, network, native button or production control.
"""
import unittest
from datetime import datetime, timezone

from edge_safety_lease import EdgeSafetyLease, EdgeSafetyLeaseConfig
from managed_runtime_safety import install_managed_runtime_safety
from runtime_safety import RuntimeSafetyError
from tests.test_edge_safety_lease import FakeHass as FakeEdge
from tests.test_runtime_edge_lease import FakeApp, live_state
from tests.test_managed_runtime_safety import V2RuntimeSafetyTests


class StartAfterDisarmTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FakeApp(state=live_state(switch="off", current=0.0, voltage=0.0))
        self.edge = FakeEdge()
        self.lease = EdgeSafetyLease(self.edge, EdgeSafetyLeaseConfig(
            ack_attempts=1, ack_delay_s=0.0,
            disarm_ack_attempts=1, disarm_ack_delay_s=0.0,
        ))
        self.app.edge_safety_lease = self.lease
        self.guard = install_managed_runtime_safety(self.app)
        self.guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        self.guard.OFF_CONFIRMATION_POLL_S = 0.0

    async def test_new_start_after_confirmed_stop_arms_first_and_resumes(self):
        self.assertTrue(await self.app.hass.turn_on())
        self.assertTrue(await self.app.hass.turn_off())
        after_stop = await self.lease.read_state()
        self.assertFalse(after_stop.armed)
        self.assertTrue(self.lease.renewals_suspended)
        assert after_stop.remaining_s == 0.0
        renew_count = self.edge.presses.count(self.lease.config.renew_entity)

        # An accepted normal START must call arm() BEFORE physical turn_on().
        self.assertTrue(await self.app.hass.turn_on())
        live = await self.lease.read_state()
        self.assertTrue(live.armed)
        self.assertEqual(live.generation, after_stop.generation + 1)
        self.assertFalse(self.lease.renewals_suspended)
        self.assertEqual(self.edge.presses.count(self.lease.config.renew_entity),
                         renew_count + 1)
        self.assertEqual(self.app.hass.live["switch"], "on")
        self.assertTrue(await self.app.hass.turn_off())

    async def test_premature_renew_after_stop_remains_fail_closed(self):
        self.assertTrue(await self.app.hass.turn_on())
        self.assertTrue(await self.app.hass.turn_off())
        self.assertTrue(self.lease.renewals_suspended)
        generation_before = (await self.lease.read_state()).generation
        count_before = self.edge.presses.count(self.lease.config.renew_entity)

        # This reproduces the error surfaced in the physical START journal;
        # renewing is forbidden before a *new* explicit arm.
        with self.assertRaisesRegex(RuntimeSafetyError, "suspended"):
            await self.guard._renew_edge_lease_or_fail(output_state=True)

        self.assertEqual(self.app.hass.live["switch"], "off")
        self.assertTrue(self.lease.renewals_suspended)
        self.assertEqual((await self.lease.read_state()).generation, generation_before)
        self.assertEqual(self.edge.presses.count(self.lease.config.renew_entity),
                         count_before)

    async def test_managed_live_read_surfaces_suspended_renewal_and_contains_output(self):
        """Pin the production call path named by the node's START journal error."""
        self.lease.suspend_renewals()
        self.assertTrue(self.lease.renewals_suspended)
        self.guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        self.guard.OFF_CONFIRMATION_POLL_S = 0.0
        self.app.hass.live = V2RuntimeSafetyTests._with_freshness(
            V2RuntimeSafetyTests._live()
        )
        raw_turn_off = self.guard._raw_turn_off

        async def turn_off_with_fresh_readback(entity_id=None):
            result = await raw_turn_off(entity_id)
            reported = datetime.now(timezone.utc).isoformat()
            self.app.hass.live["_meta"]["switch"].update(
                last_reported=reported, last_updated=reported
            )
            return result

        self.app.hass.turn_off = turn_off_with_fresh_readback
        self.guard._raw_turn_off = turn_off_with_fresh_readback

        with self.assertLogs("rd6018", level="WARNING") as captured:
            with self.assertRaisesRegex(RuntimeSafetyError, "suspended"):
                await self.app.hass.get_all_live()

        self.assertTrue(any(
            "Managed live read requests edge renewal while suspended" in line
            for line in captured.output
        ), captured.output)
        self.assertEqual(self.app.hass.live["switch"], "off")
        self.assertTrue(self.lease.renewals_suspended)
        self.assertNotIn(self.lease.config.renew_entity, self.edge.presses)


if __name__ == "__main__":
    unittest.main()
