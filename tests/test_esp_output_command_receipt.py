import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.physical.transports.esp128 import ESPHomeTransport
from runtime.config.models import PhysicalTransportConfig, ConnectionConfig, RDConfig


TextSensorInfo = type("TextSensorInfo", (), {})
TextSensorState = type("TextSensorState", (), {})


def make_transport(applied=True, awaitable=False, terminal_state=None, reported_target=None):
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
        calls = []

        def execute_service(self, service, data):
            self.calls.append((service, data))
            def emit():
                receipt = {"request_id": data["request_id"],
                           "target": bool(data["enabled"]) if reported_target is None else reported_target,
                           "state": terminal_state or ("APPLIED" if applied else "OUTCOME_UNCERTAIN"),
                           "observed_r18": (1 if data["enabled"] else 0) if reported_target is None else (1 if reported_target else 0)}
                state = TextSensorState()
                state.key = 7
                state.state = json.dumps(receipt)
                transport._on_state(state)
            if awaitable:
                async def delayed():
                    emit()
                return delayed()
            emit()
            return None

    client = Client()
    transport.client = client
    async def ensure():
        return None
    transport._ensure_state_subscription = ensure
    return transport, client


class ESPOutputCommandReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_service_and_v36_send_only_receipt(self):
        transport, client = make_transport()
        result = await transport.command_output(True)
        self.assertEqual(result["state"], "APPLIED")
        self.assertEqual(len(client.calls), 1)
        service, payload = client.calls[0]
        self.assertEqual(service.name, "rd6018_output_command")
        self.assertEqual(set(payload), {"request_id", "enabled"})
        self.assertTrue(payload["enabled"])
        self.assertEqual(transport._output_receipts, {})

    async def test_v46_awaitable_service_result(self):
        transport, client = make_transport(awaitable=True)
        self.assertEqual((await transport.command_output(False))["state"], "APPLIED")
        self.assertFalse(client.calls[0][1]["enabled"])

    async def test_uncertain_receipt_fails_without_reissuing(self):
        transport, client = make_transport(applied=False)
        with self.assertRaisesRegex(RuntimeError, "OUTCOME_UNCERTAIN"):
            await transport.command_output(True)
        self.assertEqual(len(client.calls), 1)


    async def test_applied_receipt_must_match_requested_target_and_readback(self):
        transport, client = make_transport(reported_target=False)
        with self.assertRaisesRegex(RuntimeError, "does not match requested R18 state"):
            await transport.command_output(True)
        self.assertEqual(len(client.calls), 1)
    async def test_timeout_fails_without_automatic_retry(self):
        transport, client = make_transport()
        transport.client.execute_service = lambda _service, data: client.calls.append((None, data))
        with patch("runtime.physical.transports.esp128.OUTPUT_COMMAND_TIMEOUT_S", 0.01):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                await transport.command_output(True)
        self.assertEqual(len(client.calls), 1)

    async def test_unmatched_request_receipt_does_not_complete_current_command(self):
        transport, client = make_transport()
        original = client.execute_service
        def emit_unmatched(service, data):
            wrong = dict(data, request_id="different-request")
            original(service, wrong)
        client.execute_service = emit_unmatched
        with patch("runtime.physical.transports.esp128.OUTPUT_COMMAND_TIMEOUT_S", 0.01):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                await transport.command_output(True)
        self.assertEqual(len(client.calls), 1)


    async def test_canceled_is_terminal_and_never_retried(self):
        transport, client = make_transport(terminal_state="CANCELED")
        with self.assertRaisesRegex(RuntimeError, "CANCELED"):
            await transport.command_output(True)
        self.assertEqual(len(client.calls), 1)

    async def test_native_disconnect_fails_fast_without_retry(self):
        transport, client = make_transport()
        def disconnect(_service, _data):
            transport._on_connection_closed(None)
        client.execute_service = disconnect
        with self.assertRaisesRegex(RuntimeError, "Native link dropped"):
            await transport.command_output(True)
        self.assertEqual(client.calls, [])
        self.assertEqual(transport._output_receipts, {})

    async def test_receipt_transitions_are_event_driven_and_latest_terminal_wins(self):
        transport, client = make_transport()
        original = client.execute_service
        def emit_transitions(service, data):
            client.calls.append((service, data))
            for state_name in ("ACCEPTED", "ACKNOWLEDGED_WAITING_READBACK", "APPLIED"):
                state = TextSensorState()
                state.key = 7
                state.state = json.dumps({
                    "request_id": data["request_id"], "target": True,
                    "state": state_name, "observed_r18": 1})
                transport._on_state(state)
        client.execute_service = emit_transitions
        receipt = await transport.command_output(True)
        self.assertEqual(receipt["state"], "APPLIED")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(transport._output_receipts, {})


    async def test_reconnect_baseline_blocks_on_before_send(self):
        transport, client = make_transport()
        transport._reconnecting_subscription = True
        with self.assertRaisesRegex(RuntimeError, "baseline is not restored"):
            await transport.command_output(True)
        self.assertEqual(client.calls, [])

    async def test_reconnect_baseline_still_allows_off_containment(self):
        transport, client = make_transport()
        transport._reconnecting_subscription = True
        receipt = await transport.command_output(False)
        self.assertEqual(receipt["state"], "APPLIED")
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(client.calls[0][1]["enabled"])
    async def test_reconnect_invalidates_receipt_cache_and_waiters(self):
        transport, _client = make_transport()
        transport._output_receipts["old"] = {"request_id": "old", "state": "APPLIED"}
        waiter = asyncio.Event()
        transport._output_receipt_events["old"] = waiter
        transport._state_cache["old"] = {"TextSensorState": "old"}
        transport._on_connection_closed(None)
        self.assertEqual(transport._output_receipts, {})
        self.assertEqual(transport._output_receipt_events, {})
        self.assertTrue(waiter.is_set())
        self.assertEqual(transport._state_cache, {})
