from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import ExecutionPort
from runtime.output.command_receipt import OutputCommandReceipt
from runtime.output.command_receipt_observation import observe_applied_on
from runtime.physical.transports.esp128 import ESPHomeTransport
from unittest.mock import AsyncMock


def receipt(name: str) -> OutputCommandReceipt:
    return OutputCommandReceipt(name, True, "APPLIED", 1, 10.0, 2,
                                '{"observed_r18":1,"request_id":"' + name
                                + '","state":"APPLIED","target":true}')


def intent() -> ExecutionIntent:
    return ExecutionIntent(14.4, 2.0, "AUTO", "decision", SafetyContext())


class B1034TasklocalReceiptTests(unittest.TestCase):
    def test_transport_observes_exact_receipt_from_one_existing_command(self):
        exact = receipt("one")
        transport = object.__new__(ESPHomeTransport)
        transport.command_output_with_receipt = AsyncMock(return_value=exact)
        seen = []

        async def run():
            from runtime.output.command_receipt_observation import begin_observation, reset_observation
            slot, token = begin_observation()
            try:
                result = await transport.command_output(True)
                seen.append(slot.receipt)
                return result
            finally:
                reset_observation(token)

        decoded = asyncio.run(run())
        self.assertEqual(decoded["request_id"], "one")
        self.assertIs(seen[0], exact)
        transport.command_output_with_receipt.assert_awaited_once_with(True)

    def test_execution_port_exposes_only_after_existing_enable_accepts(self):
        exact = receipt("accepted")

        class Owner:
            def __init__(self, accepted=True, raises=False):
                self.accepted, self.raises, self.calls = accepted, raises, 0

            async def safe_enable_output(self, **kwargs):
                self.calls += 1
                observe_applied_on(exact)
                if self.raises:
                    raise RuntimeError("failed final acceptance")
                return SimpleNamespace(enabled=self.accepted, detail="test")

        async def run(owner):
            delivered = []
            port = ExecutionPort(owner)
            result = await port.enable(intent(), identity=SimpleNamespace(),
                                       recipe_voltage_ceiling_v=16.0,
                                       on_receipt_observed=delivered.append)
            return result, delivered

        owner = Owner()
        result, delivered = asyncio.run(run(owner))
        self.assertTrue(result.accepted)
        self.assertEqual(owner.calls, 1)
        self.assertEqual(len(delivered), 1)
        self.assertIs(delivered[0], exact)

        for owner in (Owner(accepted=False), Owner(raises=True)):
            with self.subTest(owner=owner):
                if owner.raises:
                    with self.assertRaisesRegex(RuntimeError, "failed final acceptance"):
                        asyncio.run(run(owner))
                else:
                    result, delivered = asyncio.run(run(owner))
                    self.assertFalse(result.accepted)
                    self.assertEqual(delivered, [])
                self.assertEqual(owner.calls, 1)

    def test_context_isolation_concurrency_and_reset(self):
        first, second = receipt("first"), receipt("second")

        async def request(value):
            from runtime.output.command_receipt_observation import begin_observation, reset_observation
            slot, token = begin_observation()
            try:
                await asyncio.sleep(0)
                observe_applied_on(value)
                await asyncio.sleep(0)
                return slot.receipt
            finally:
                reset_observation(token)

        async def run():
            a, b = await asyncio.gather(request(first), request(second))
            from runtime.output.command_receipt_observation import begin_observation, reset_observation
            slot, token = begin_observation()
            try:
                return a, b, slot.receipt
            finally:
                reset_observation(token)

        a, b, empty = asyncio.run(run())
        self.assertIs(a, first)
        self.assertIs(b, second)
        self.assertIsNone(empty)

    def test_non_native_and_non_applied_receipts_are_not_observed(self):
        from runtime.output.command_receipt_observation import begin_observation, reset_observation
        slot, token = begin_observation()
        try:
            observe_applied_on({"request_id": "ha102"})
            observe_applied_on(OutputCommandReceipt("off", False, "APPLIED", 0, 10.0, 2, "{}"))
            observe_applied_on(OutputCommandReceipt("failed", True, "FAILED", 1, 10.0, 2, "{}"))
            self.assertIsNone(slot.receipt)
        finally:
            reset_observation(token)


if __name__ == "__main__":
    unittest.main()
