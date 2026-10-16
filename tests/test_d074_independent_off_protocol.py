"""D074 pure async D061 OFF adapter protocol: mocks only, no live endpoint."""
import asyncio
from dataclasses import replace
import time
import unittest

from tools.acceptance_guard.fixture_supervisor import Readback, LeaseReadback
from tools.acceptance_guard.independent_off_protocol import (
    OffAdapters, NativeEvidence, IndependentLeaseEvidence,
    OffOutcome, independent_off_then_disarm, readiness,
)


class D074IndependentOffProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.actions = []

    def adapters(self, *, same_origin=False, output=False, stale=False,
                 disarm_ok=True, lease_source="edge-direct", delayed_off=0.0,
                 off_ack=True, lease_armed=False):
        async def off(cutoff):
            self.actions.append(("off", cutoff))
            if delayed_off:
                await asyncio.sleep(delayed_off)
            return off_ack

        def sample(name, origin, path):
            stamp = time.monotonic() - (15.0 if stale else 0.0)
            return NativeEvidence(
                Readback(name, name + "-report", stamp, output, 0.0, 0.0, "NORMAL"),
                origin, path, True,
            )

        async def read_a(cutoff):
            self.actions.append(("read-a", cutoff))
            return sample("ha-native", "ha-rd-register", "ha-socket")

        async def read_b(cutoff):
            self.actions.append(("read-b", cutoff))
            return sample("esp-native", "ha-rd-register" if same_origin else "esp-rd-register",
                          "esp-socket")

        async def disarm(cutoff):
            self.actions.append(("disarm", cutoff))
            return disarm_ok

        async def lease(cutoff):
            self.actions.append(("lease", cutoff))
            return IndependentLeaseEvidence(
                LeaseReadback(lease_source, "lease-read", time.monotonic(), lease_armed),
                lease_source, lease_source + "-native", True,
            )
        return OffAdapters(off, read_a, read_b, disarm, lease)

    async def test_default_has_no_live_adapter_or_io(self):
        self.assertEqual(
            readiness(OffAdapters()),
            OffOutcome.BLOCKED_NO_INDEPENDENT_OFF_ADAPTER,
        )
        result = await independent_off_then_disarm(OffAdapters())
        self.assertEqual(result.outcome, OffOutcome.BLOCKED_NO_INDEPENDENT_OFF_ADAPTER)
        self.assertEqual(self.actions, [])

    async def test_missing_second_native_source_never_disarms(self):
        a = self.adapters()
        result = await independent_off_then_disarm(replace(a, native_read_b=None))
        self.assertEqual(result.outcome, OffOutcome.BLOCKED_NO_INDEPENDENT_READBACK)
        self.assertEqual(self.actions, [])

    async def test_good_independent_sequence_and_one_deadline(self):
        receipt = await independent_off_then_disarm(self.adapters())
        self.assertEqual(receipt.outcome, OffOutcome.LEASE_DISARMED)
        self.assertTrue(receipt.off_independently_proved)
        self.assertTrue(receipt.lease_independently_disarmed)
        self.assertEqual(self.actions[0][0], "off")
        self.assertEqual({x[1] for x in self.actions}, {self.actions[0][1]})
        self.assertEqual([x[0] for x in self.actions][-2:], ["disarm", "lease"])

    async def test_two_ha_proxies_of_same_physical_producer_rejected(self):
        receipt = await independent_off_then_disarm(self.adapters(same_origin=True))
        self.assertEqual(receipt.outcome, OffOutcome.HOLD)
        self.assertEqual(receipt.reason, "off_report_sources_not_independent")
        self.assertNotIn("disarm", [x[0] for x in self.actions])

    async def test_output_on_or_stale_native_readback_is_hold(self):
        for opts in ({"output": True}, {"stale": True}):
            with self.subTest(opts=opts):
                self.actions.clear()
                receipt = await independent_off_then_disarm(self.adapters(**opts))
                self.assertEqual(receipt.outcome, OffOutcome.HOLD)
                self.assertFalse(receipt.off_independently_proved)
                self.assertNotIn("disarm", [x[0] for x in self.actions])

    async def test_command_rejected_keeps_all_readback_unreached(self):
        receipt = await independent_off_then_disarm(self.adapters(off_ack=False))
        self.assertEqual(receipt.outcome, OffOutcome.HOLD)
        self.assertEqual([x[0] for x in self.actions], ["off"])

    async def test_disarm_rejection_does_not_call_lease_readback(self):
        receipt = await independent_off_then_disarm(self.adapters(disarm_ok=False))
        self.assertEqual(receipt.outcome, OffOutcome.HOLD)
        self.assertTrue(receipt.off_independently_proved)
        self.assertFalse(receipt.lease_independently_disarmed)
        self.assertNotIn("lease", [x[0] for x in self.actions])

    async def test_third_lease_source_must_be_independent_and_disarmed(self):
        for opts in ({"lease_source": "ha-rd-register"}, {"lease_armed": True}):
            with self.subTest(opts=opts):
                self.actions.clear()
                receipt = await independent_off_then_disarm(self.adapters(**opts))
                self.assertEqual(receipt.outcome, OffOutcome.HOLD)
                self.assertFalse(receipt.lease_independently_disarmed)

    async def test_timeout_of_independent_command_not_success(self):
        receipt = await independent_off_then_disarm(
            self.adapters(delayed_off=0.15), deadline_s=0.03
        )
        self.assertEqual(receipt.outcome, OffOutcome.HOLD)
        self.assertFalse(receipt.off_independently_proved)
        self.assertEqual([x[0] for x in self.actions], ["off"])

    async def test_errors_do_not_bypass_off_proof(self):
        a = self.adapters()
        async def broken(_):
            raise ConnectionError("fixture only")
        receipt = await independent_off_then_disarm(replace(a, native_read_b=broken))
        self.assertEqual(receipt.outcome, OffOutcome.HOLD)
        self.assertNotIn("disarm", [x[0] for x in self.actions])

    async def test_cancel_propagates_to_external_supervisor(self):
        a = self.adapters(delayed_off=10)
        task = asyncio.create_task(independent_off_then_disarm(a))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn("disarm", [x[0] for x in self.actions])

    async def test_invalid_deadline_rejected_before_adapter(self):
        for deadline in (0, -1, 45.00001, float("nan")):
            with self.subTest(deadline=deadline):
                with self.assertRaises(ValueError):
                    await independent_off_then_disarm(self.adapters(), deadline_s=deadline)
        self.assertEqual(self.actions, [])


if __name__ == "__main__":
    unittest.main()
