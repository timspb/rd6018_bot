from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

from application.execution_port import ExecutionPort
from hass_api import HassClient
from runtime.config.models import ConnectionConfig, PhysicalTransportConfig, RDConfig
from runtime.physical.connectors.esp_direct import ESPDirectConnector
from runtime.physical.connectors.ha_esp import HAESPConnector
from runtime.physical.transports.esp128 import ESPHomeTransport, OutputCommandReceipt
from runtime.safety.runtime_guard import RuntimeSafetyGuard


TextSensorInfo = type("TextSensorInfo", (), {})
TextSensorState = type("TextSensorState", (), {})


def make_stack(*, emit=True, terminal_state="APPLIED", observed_r18=0):
    config = PhysicalTransportConfig(
        name="esp128", type="esphome", enabled=True, priority=1,
        connection=ConnectionConfig("127.0.0.1", 6053),
        entities={"output_command_status": "rd6018_output_command_status"},
    )
    transport = ESPHomeTransport(config, RDConfig(60.0, 18.0, 1000.0))
    entity = TextSensorInfo()
    entity.object_id = "rd6018_output_command_status"
    entity.key = 7
    entity.device_id = 1
    transport.entities = (entity,)
    transport._entities_by_key = {7: [entity]}
    transport.services = (SimpleNamespace(name="rd6018_output_command"),)

    class Client:
        is_connected = True

        def execute_service(self, _service, data):
            if emit:
                state = TextSensorState()
                state.key = 7
                state.state = json.dumps({
                    "request_id": data["request_id"], "target": False,
                    "state": terminal_state, "observed_r18": observed_r18,
                })
                transport._on_state(state)

    transport.client = Client()

    async def ensure_subscription():
        return None

    transport._ensure_state_subscription = ensure_subscription
    original_command = transport.command_output_with_receipt

    async def capture_receipt(enabled):
        transport.last_receipt = await original_command(enabled)
        return transport.last_receipt

    transport.command_output_with_receipt = capture_receipt
    connector = ESPDirectConnector.__new__(ESPDirectConnector)
    connector.transport = transport
    hass = HassClient("", "", backend=connector)
    guard = RuntimeSafetyGuard(SimpleNamespace(hass=hass))
    port = ExecutionPort(guard)
    return transport, connector, hass, guard, port


class TypedOffReceiptAD095Tests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_applied_receipt_propagates_through_existing_owners(self):
        transport, connector, hass, guard, port = make_stack()
        receipt = await port.request_emergency_off_receipt()
        self.assertIsInstance(receipt, OutputCommandReceipt)
        self.assertIs(receipt, transport.last_receipt)
        self.assertTrue(hass.supports_typed_off_receipt)
        self.assertEqual(receipt.requested_target, False)
        self.assertEqual(receipt.terminal_status, "APPLIED")
        self.assertEqual(receipt.observed_r18, 0)
        self.assertEqual(receipt.connection_generation, connector.native_connection_generation)
        self.assertGreater(receipt.terminal_completed_monotonic, 0)
        with self.assertRaises((AttributeError, TypeError)):
            receipt.terminal_status = "CANCELED"

    async def test_guard_rejects_invalid_or_stale_terminal_evidence(self):
        _transport, connector, hass, guard, _port = make_stack()
        raw = {"request_id": "request", "target": False, "state": "APPLIED", "observed_r18": 0}
        good = OutputCommandReceipt("request", False, "APPLIED", 0, 1.0, 0,
                                    json.dumps(raw, sort_keys=True, separators=(",", ":")))

        def matching(**updates):
            altered = dict(raw, **updates)
            return replace(
                good,
                requested_target=altered["target"],
                terminal_status=altered["state"],
                observed_r18=altered["observed_r18"],
                raw_terminal_identity=json.dumps(altered, sort_keys=True, separators=(",", ":")),
            )

        cases = [
            matching(target=True),
            matching(state="OUTCOME_UNCERTAIN"),
            matching(state="CANCELED"),
            replace(good, terminal_completed_monotonic=float("nan")),
            matching(observed_r18=1),
            replace(good, connection_generation=1),
            replace(good, raw_terminal_identity="{}"),
        ]
        for candidate in cases:
            guard._raw_turn_off_with_receipt = lambda value=candidate: asyncio.sleep(0, result=value)
            self.assertIsNone(await guard.turn_off_with_receipt())
        connector.transport._native_connection_generation = 2
        guard._raw_turn_off_with_receipt = lambda: asyncio.sleep(0, result=good)
        self.assertIsNone(await guard.turn_off_with_receipt())

    async def test_transport_uncertainty_and_timeout_produce_no_typed_evidence(self):
        transport, _connector, _hass, _guard, port = make_stack(emit=False)
        from unittest.mock import patch

        with patch("runtime.physical.transports.esp128.OUTPUT_COMMAND_TIMEOUT_S", 0.001):
            self.assertIsNone(await port.request_emergency_off_receipt())
        self.assertEqual(transport._output_receipts, {})

    async def test_non_applied_and_mismatched_readback_never_escape_transport(self):
        for state, observed in (("OUTCOME_UNCERTAIN", 0), ("CANCELED", 0), ("APPLIED", 1)):
            _transport, _connector, _hass, _guard, port = make_stack(
                terminal_state=state, observed_r18=observed,
            )
            self.assertIsNone(await port.request_emergency_off_receipt())

    async def test_unsupported_connector_is_explicit_and_fail_closed(self):
        hass = HassClient("", "", backend=HAESPConnector.__new__(HAESPConnector))
        guard = RuntimeSafetyGuard(SimpleNamespace(hass=hass))
        port = ExecutionPort(guard)
        self.assertFalse(hass.supports_typed_off_receipt)
        self.assertIsNone(await hass.turn_off_with_receipt())
        self.assertIsNone(await port.request_emergency_off_receipt())


if __name__ == "__main__":
    unittest.main()
