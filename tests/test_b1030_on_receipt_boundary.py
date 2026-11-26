from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from application.execution_port import ExecutionPort
from hass_api import HassClient
from runtime.output.command_receipt import OutputCommandReceipt
from runtime.physical.connectors.esp_direct import ESPDirectConnector
from runtime.physical.transports.esp128 import ESPHomeTransport
from runtime.safety.managed_guard import ManagedRuntimeSafetyGuard
from runtime.safety.runtime_guard import RuntimeSafetyGuard
from runtime.safety.strict_guard import StrictRuntimeSafetyGuard


def receipt() -> OutputCommandReceipt:
    return OutputCommandReceipt(
        request_id="request-1",
        requested_target=True,
        terminal_status="APPLIED",
        observed_r18=1,
        terminal_completed_monotonic=10.0,
        connection_generation=2,
        raw_terminal_identity='{"observed_r18":1,"request_id":"request-1",'
        '"state":"APPLIED","target":true}',
    )


class B1030OnReceiptBoundaryTests(unittest.TestCase):
    def test_direct_transport_and_connector_reduce_the_typed_receipt(self):
        exact_receipt = receipt()
        transport = object.__new__(ESPHomeTransport)
        transport.command_output_with_receipt = AsyncMock(return_value=exact_receipt)

        decoded = asyncio.run(transport.command_output(True))
        self.assertEqual(decoded["request_id"], exact_receipt.request_id)
        self.assertIsNot(decoded, exact_receipt)
        transport.command_output_with_receipt.assert_awaited_once_with(True)

        connector = object.__new__(ESPDirectConnector)
        connector.transport = AsyncMock()
        connector.transport.command_output.return_value = decoded
        result = asyncio.run(connector.enable_output())
        self.assertIsNone(result)
        connector.transport.command_output.assert_awaited_once_with(True)

    def test_hass_turn_on_discards_backend_return_and_preserves_bool(self):
        exact_receipt = receipt()

        class Backend:
            def __init__(self):
                self.calls = 0

            async def enable_output(self):
                self.calls += 1
                return exact_receipt

        backend = Backend()
        client = HassClient("", "", backend=backend)
        result = asyncio.run(client.turn_on())
        self.assertIs(result, True)
        self.assertEqual(backend.calls, 1)

    def test_execution_port_keeps_single_bool_call_and_guard_mro_is_overridden(self):
        class Owner:
            def __init__(self, outcome):
                self.outcome = outcome
                self.calls = 0

            async def turn_on(self):
                self.calls += 1
                return self.outcome

        for outcome in (True, False):
            owner = Owner(outcome)
            result = asyncio.run(ExecutionPort(owner).request_verified_on())
            self.assertIs(result, outcome)
            self.assertEqual(owner.calls, 1)

        self.assertIs(ManagedRuntimeSafetyGuard.__mro__[1], StrictRuntimeSafetyGuard)
        self.assertIs(ManagedRuntimeSafetyGuard.__mro__[2], RuntimeSafetyGuard)
        self.assertIsNot(
            ManagedRuntimeSafetyGuard.turn_on,
            StrictRuntimeSafetyGuard.turn_on,
        )
        self.assertIsNot(StrictRuntimeSafetyGuard.turn_on, RuntimeSafetyGuard.turn_on)


if __name__ == "__main__":
    unittest.main()
