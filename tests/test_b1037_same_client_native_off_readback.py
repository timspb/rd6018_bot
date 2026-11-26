from __future__ import annotations

import asyncio
import time
import unittest
from types import SimpleNamespace

from application.execution_port import ExecutionPort
from runtime.output.command_receipt import OutputCommandReceipt
from runtime.output.command_receipt_observation import (
    begin_observation, observe_applied_off, reset_observation,
)
from runtime.physical.transports.esp128 import ESPHomeTransport


class SensorInfo:
    def __init__(self, object_id, key, device_id=1):
        self.object_id, self.key, self.device_id = object_id, key, device_id


class SensorState:
    def __init__(self, key, state):
        self.key, self.state = key, state


def valid_receipt(name="off"):
    return OutputCommandReceipt(name, False, "APPLIED", 0,
                                time.monotonic() - 0.05, 7, "terminal")


class B1037OffPhaseTests(unittest.TestCase):
    def make_transport(self):
        transport = ESPHomeTransport.__new__(ESPHomeTransport)
        transport.config = SimpleNamespace(entities={
            "output_state": "r18", "voltage": "voltage", "current": "current",
        })
        transport.client = object()
        transport._native_connection_generation = 7
        transport._reconnecting_subscription = False
        transport.entities = tuple(SensorInfo(name, key) for name, key in
                                   (("r18", 1), ("voltage", 2), ("current", 3)))
        transport._entities_by_key = {item.key: [item] for item in transport.entities}
        transport._native_callback_records = {}
        transport._state_cache = {}
        transport._state_updated_at = {}
        transport._state_reported_at = {}
        transport._state_types = {}
        return transport

    def emit(self, transport, values=(0, 0.0, 0.0)):
        generation = transport._native_connection_generation
        for key, value in enumerate(values, 1):
            transport._on_state(SensorState(key, value), connection_generation=generation,
                                source_client=transport.client)

    def observe(self, transport, receipt):
        slot, token = begin_observation()
        try:
            observe_applied_off(receipt, source_transport=transport,
                                source_client=transport.client)
            return slot, transport.get_post_on_native_phase(receipt)
        finally:
            reset_observation(token)

    def test_post_off_zero_phase_is_same_client_and_exact_receipt(self):
        transport = self.make_transport()
        receipt = valid_receipt()
        self.emit(transport)
        slot, result = self.observe(transport, receipt)
        self.assertIs(slot.receipt, receipt)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(result["records"]["output_r18"]["value"], 0)
        self.assertEqual(result["records"]["voltage_v"]["value"], 0.0)
        self.assertEqual(result["records"]["current_a"]["value"], 0.0)

    def test_off_phase_rejects_stale_preterminal_wrong_values_and_changed_origin(self):
        for label, values, age, origin in (
            ("r18_on", (1, 0.0, 0.0), 0.1, "same"),
            ("voltage", (0, 0.01, 0.0), 0.1, "same"),
            ("current", (0, 0.0, 0.01), 0.1, "same"),
            ("stale", (0, 0.0, 0.0), 9.0, "same"),
            ("preterminal", (0, 0.0, 0.0), 0.1, "same"),
            ("foreign_client", (0, 0.0, 0.0), 0.1, "client"),
            ("foreign_transport", (0, 0.0, 0.0), 0.1, "transport"),
        ):
            with self.subTest(label=label):
                transport = self.make_transport()
                self.emit(transport, values)
                if age > 1:
                    for key, (state, _ts, gen, client, source) in list(transport._native_callback_records.items()):
                        transport._native_callback_records[key] = (state, time.monotonic()-age,
                                                                   gen, client, source)
                receipt = valid_receipt()
                if label == "foreign_client":
                    client = object()
                    slot, token = begin_observation()
                    try:
                        observe_applied_off(receipt, source_transport=transport, source_client=client)
                        result = transport.get_post_on_native_phase(receipt)
                    finally:
                        reset_observation(token)
                elif label == "foreign_transport":
                    slot, token = begin_observation()
                    try:
                        observe_applied_off(receipt, source_transport=object(), source_client=transport.client)
                        result = transport.get_post_on_native_phase(receipt)
                    finally:
                        reset_observation(token)
                else:
                    # Make otherwise fresh callbacks predate this terminal receipt.
                    if label == "preterminal":
                        receipt = OutputCommandReceipt("pre", False, "APPLIED", 0,
                                                       time.monotonic()+1, 7, "terminal")
                    _, result = self.observe(transport, receipt)
                self.assertEqual(result["status"], "NOT_OBSERVED")

    def test_transport_generation_and_sensor_types_are_required(self):
        transport = self.make_transport()
        self.emit(transport)
        receipt = valid_receipt()
        transport._native_connection_generation = 8
        self.assertEqual(self.observe(transport, receipt)[1]["status"], "NOT_OBSERVED")

        transport = self.make_transport()
        transport.entities = (transport.entities[0],
                             SimpleNamespace(object_id="voltage", key=2, device_id=1),
                             transport.entities[2])
        self.emit(transport)
        self.assertEqual(self.observe(transport, valid_receipt())[1]["status"], "NOT_OBSERVED")

        transport = self.make_transport()
        self.emit(transport)
        key = ("SensorInfo", 2)
        state, timestamp, generation, client, source = transport._native_callback_records[key]
        transport._native_callback_records[key] = (state, "bad-time", generation, client, source)
        self.assertEqual(self.observe(transport, valid_receipt())[1]["status"], "NOT_OBSERVED")

    def test_actual_emergency_off_route_captures_receipt_and_reads_same_transport(self):
        from tests.test_typed_off_receipt_ad095 import make_stack

        transport, connector, _hass, _guard, port = make_stack()
        transport.config.entities.update({
            "output_state": "r18", "voltage": "voltage", "current": "current",
        })
        physical = [SensorInfo("r18", 1), SensorInfo("voltage", 2),
                    SensorInfo("current", 3)]
        transport.entities = tuple(transport.entities) + tuple(physical)
        transport._entities_by_key.update({item.key: [item] for item in physical})
        original = transport.command_output_with_receipt
        command_targets = []

        async def command_then_native_callbacks(enabled):
            command_targets.append(enabled)
            receipt = await original(enabled)
            if not enabled:
                self.emit(transport)
            return receipt

        transport.command_output_with_receipt = command_then_native_callbacks
        delivered = []
        returned = asyncio.run(port.request_emergency_off_receipt(
            on_native_off_observed=lambda receipt, sample: delivered.append((receipt, sample))))
        self.assertIs(returned, transport.last_receipt)
        self.assertEqual(command_targets, [False])
        self.assertEqual(delivered[0][1]["status"], "OBSERVED", delivered[0][1])
        self.assertIs(delivered[0][0], returned)
        self.assertEqual(connector.native_connection_generation, returned.connection_generation)

    def test_optional_execution_port_callback_preserves_single_command_and_return_identity(self):
        receipt = valid_receipt()

        class Owner:
            def __init__(self, result=receipt, fail=False):
                self.result, self.fail, self.calls = result, fail, 0

            async def turn_off_with_receipt(self):
                self.calls += 1
                if self.fail:
                    raise RuntimeError("off failed")
                observe_applied_off(self.result, source_transport=self,
                                    source_client=self)
                return self.result

            def get_post_on_native_phase(self, seen):
                self.seen = seen
                return {"status": "NOT_OBSERVED"}

        async def run(owner):
            delivered = []
            result = await ExecutionPort(owner).request_emergency_off_receipt(
                on_native_off_observed=lambda seen, sample: delivered.append((seen, sample)))
            return result, delivered

        owner = Owner()
        result, delivered = asyncio.run(run(owner))
        self.assertIs(result, receipt)
        self.assertEqual(owner.calls, 1)
        self.assertEqual(delivered[0][0], receipt)
        self.assertEqual(delivered[0][1]["status"], "NOT_OBSERVED")

        for owner in (Owner(fail=True), Owner(result=None), Owner(result=False)):
            result, delivered = asyncio.run(run(owner))
            self.assertIsNone(result)
            self.assertEqual(delivered, [])
            self.assertEqual(owner.calls, 1)

        class UnsupportedOwner:
            pass

        result, delivered = asyncio.run(run(UnsupportedOwner()))
        self.assertIsNone(result)
        self.assertEqual(delivered, [])


if __name__ == "__main__":
    unittest.main()
