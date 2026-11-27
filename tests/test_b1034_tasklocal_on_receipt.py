from __future__ import annotations

import asyncio
import unittest
import time
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
    def _read_same_client(self, transport, receipt_obj):
        from runtime.output.command_receipt_observation import begin_observation, reset_observation
        slot, token = begin_observation()
        try:
            observe_applied_on(receipt_obj, source_transport=transport, source_client=transport.client)
            return transport.get_post_on_native_phase(receipt_obj)
        finally:
            reset_observation(token)

    def test_transport_observes_exact_receipt_from_one_existing_command(self):
        exact = receipt("one")
        transport = object.__new__(ESPHomeTransport)
        transport.client = object()
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

    def test_post_on_phase_is_optional_and_does_not_change_enable_result_or_dispatch(self):
        exact = receipt("accepted_phase")
        phase = {"status": "NOT_OBSERVED", "reason": "stale"}

        class Owner:
            calls = 0
            async def safe_enable_output(self, **kwargs):
                self.calls += 1
                observe_applied_on(exact)
                return SimpleNamespace(enabled=True, detail="same")
            def get_post_on_native_phase(self, observed_receipt):
                self.assertion = observed_receipt is exact
                return phase

        async def run():
            owner = Owner()
            delivered = []
            port = ExecutionPort(owner)
            result = await port.enable(
                intent(), identity=SimpleNamespace(), recipe_voltage_ceiling_v=16.0,
                on_native_phase_observed=lambda observed_receipt, sample:
                    delivered.append((observed_receipt, sample)),
            )
            return owner, result, delivered

        owner, result, delivered = asyncio.run(run())
        self.assertTrue(result.accepted)
        self.assertTrue(result.verified)
        self.assertEqual(result.operation, "enable")
        self.assertEqual(owner.calls, 1)
        self.assertTrue(owner.assertion)
        self.assertIs(delivered[0][0], exact)
        self.assertIs(delivered[0][1], phase)

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

    def test_same_transport_post_on_phase_keeps_typed_callback_objects(self):
        class SensorInfo:
            def __init__(self, object_id, key):
                self.object_id, self.key, self.device_id = object_id, key, 4

        class SensorState:
            def __init__(self, key, state):
                self.key, self.state = key, state

        transport = ESPHomeTransport.__new__(ESPHomeTransport)
        transport.config = SimpleNamespace(entities={
            "output_state": "r18", "voltage": "voltage", "current": "current",
        })
        transport.client = object()
        transport._native_connection_generation = 3
        transport._reconnecting_subscription = False
        entities = [SensorInfo("r18", 1), SensorInfo("voltage", 2), SensorInfo("current", 3)]
        transport.entities = tuple(entities)
        transport._entities_by_key = {item.key: [item] for item in entities}
        transport._native_callback_records = {}
        transport._state_cache = {}
        transport._state_updated_at = {}
        transport._state_reported_at = {}
        transport._state_types = {}
        raw = [SensorState(1, 1), SensorState(2, 14.2), SensorState(3, 0.8)]
        for item in raw:
            transport._on_state(item, connection_generation=3, source_client=transport.client)
        completed = time.monotonic() - 0.3
        valid_receipt = OutputCommandReceipt("phase", True, "APPLIED", 1, completed, 3, "raw")
        result = self._read_same_client(transport, valid_receipt)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertIs(result["records"]["output_r18"]["state"], raw[0])
        self.assertEqual(result["records"]["voltage_v"]["device_id"], 4)
        self.assertEqual(result["records"]["current_a"]["native_type"], "SensorState")
        self.assertTrue(all(item["subscription_timestamp_monotonic"] > completed
                            for item in result["records"].values()))
        # Source object provenance is not implied by a matching generation.
        from runtime.output.command_receipt_observation import begin_observation, reset_observation
        _, bad_token = begin_observation()
        try:
            observe_applied_on(valid_receipt, source_transport=object(), source_client=transport.client)
            self.assertEqual(transport.get_post_on_native_phase(valid_receipt)["reason"],
                             "command_transport_origin_mismatch")
        finally:
            reset_observation(bad_token)

        # Even same-source callbacks must satisfy the existing 8s age bound.
        aged = dict(transport._native_callback_records)
        key = ("SensorInfo", 2)
        st, ts, gen, cli, src = aged[key]
        aged[key] = (st, time.monotonic()-9.0, gen, cli, src)
        transport._native_callback_records = aged
        expired_receipt = OutputCommandReceipt("aged", True, "APPLIED", 1,
                                               time.monotonic()-10.0, 3, "raw")
        self.assertEqual(self._read_same_client(transport, expired_receipt)["status"],
                         "NOT_OBSERVED")
        transport._native_callback_records = dict(aged)
        transport._native_callback_records[key] = (st, ts, gen, cli, src)

        stale = dict(transport._native_callback_records)
        key = ("SensorInfo", 2)
        state, _timestamp, generation, client, source = stale[key]
        stale[key] = (state, 9.0, generation, client, source)
        transport._native_callback_records = stale
        self.assertEqual(self._read_same_client(transport,
            OutputCommandReceipt("phase", True, "APPLIED", 1, 10.0, 3, "raw")
        )["status"], "NOT_OBSERVED")

    def test_same_transport_phase_rejects_stale_generation_and_number_only(self):
        class SensorInfo:
            object_id, key, device_id = "r18", 1, 1

        class NumberInfo:
            object_id, key, device_id = "voltage", 2, 1

        class SensorState:
            def __init__(self, key, state):
                self.key, self.state = key, state

        transport = ESPHomeTransport.__new__(ESPHomeTransport)
        transport.config = SimpleNamespace(entities={
            "output_state": "r18", "voltage": "voltage", "current": "current",
        })
        transport.client = object()
        transport._native_connection_generation = 2
        transport._reconnecting_subscription = False
        current_info = type("SensorInfo", (), {
            "object_id": "current", "key": 3, "device_id": 1,
        })()
        output_info = SensorInfo()
        transport.entities = (output_info, NumberInfo(), current_info)
        recent = time.monotonic() - 0.1
        transport._native_callback_records = {
            ("SensorInfo", 1): (SensorState(1, 1), recent, 2, transport.client, transport),
            ("SensorInfo", 3): (SensorState(3, 1.0), recent, 2, transport.client, transport),
        }
        transport._on_state = lambda *args, **kwargs: None
        result = self._read_same_client(transport, receipt("phase"))
        self.assertEqual(result["status"], "NOT_OBSERVED")
        self.assertEqual(result["reason"], "native_sensor_missing_or_ambiguous")
        same_generation_receipt = OutputCommandReceipt("r", True, "APPLIED", 1, recent-1.0, 2, "raw")
        result = self._read_same_client(transport, same_generation_receipt)
        self.assertEqual(result["status"], "NOT_OBSERVED")
        self.assertEqual(result["reason"], "native_sensor_missing_or_ambiguous")

    def test_same_integer_generation_from_different_transport_client_is_rejected(self):
        from runtime.output.command_receipt import OutputCommandReceipt

        class SensorInfo:
            def __init__(self, object_id, key):
                self.object_id, self.key, self.device_id = object_id, key, 1

        class SensorState:
            def __init__(self, key, state):
                self.key, self.state = key, state

        transport = ESPHomeTransport.__new__(ESPHomeTransport)
        transport.config = SimpleNamespace(entities={
            "output_state": "r18", "voltage": "voltage", "current": "current",
        })
        old_client, transport.client = object(), object()
        transport._native_connection_generation = 5
        transport._reconnecting_subscription = False
        entities = [SensorInfo("r18", 1), SensorInfo("voltage", 2), SensorInfo("current", 3)]
        transport.entities = tuple(entities)
        transport._entities_by_key = {item.key: [item] for item in entities}
        transport._native_callback_records = {}
        transport._state_cache = {}
        transport._state_updated_at = {}
        transport._state_reported_at = {}
        transport._state_types = {}
        for state in (SensorState(1, 1), SensorState(2, 14.0), SensorState(3, 1.0)):
            transport._on_state(state, connection_generation=5, source_client=old_client)
        result = self._read_same_client(transport,
            OutputCommandReceipt("phase", True, "APPLIED", 1, 10.0, 5, "raw")
        )
        self.assertEqual(result["status"], "NOT_OBSERVED")
        self.assertEqual(result["reason"], "native_callback_missing")

    def test_same_client_and_generation_from_different_transport_instance_is_rejected(self):
        from runtime.output.command_receipt import OutputCommandReceipt

        class SensorInfo:
            def __init__(self, object_id, key):
                self.object_id, self.key, self.device_id = object_id, key, 1

        class SensorState:
            def __init__(self, key, state):
                self.key, self.state = key, state

        first = ESPHomeTransport.__new__(ESPHomeTransport)
        second = ESPHomeTransport.__new__(ESPHomeTransport)
        for transport in (first, second):
            transport.config = SimpleNamespace(entities={
                "output_state": "r18", "voltage": "voltage", "current": "current",
            })
            transport._native_connection_generation = 6
            transport._reconnecting_subscription = False
            entities = [SensorInfo("r18", 1), SensorInfo("voltage", 2), SensorInfo("current", 3)]
            transport.entities = tuple(entities)
            transport._entities_by_key = {item.key: [item] for item in entities}
            transport._native_callback_records = {}
            transport._state_cache = {}
            transport._state_updated_at = {}
            transport._state_reported_at = {}
            transport._state_types = {}
        shared_client = object()
        first.client = second.client = shared_client
        for state in (SensorState(1, 1), SensorState(2, 14.0), SensorState(3, 0.7)):
            first._on_state(state, connection_generation=6, source_client=shared_client)
        second._native_callback_records = dict(first._native_callback_records)
        result = self._read_same_client(second,
            OutputCommandReceipt("phase", True, "APPLIED", 1, 10.0, 6, "raw")
        )
        self.assertEqual(result["status"], "NOT_OBSERVED")
        self.assertEqual(result["reason"], "native_callback_not_post_on_same_connection")

    def test_ha_backend_does_not_produce_native_phase(self):
        from hass_api import HassClient
        client = HassClient(backend=object())
        self.assertEqual(client.get_post_on_native_phase(receipt("ha"))["status"], "NOT_OBSERVED")


if __name__ == "__main__":
    unittest.main()
