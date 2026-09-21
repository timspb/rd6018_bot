import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.config.models import ConnectionConfig, PhysicalTransportConfig, RDConfig
from runtime.physical.transports.esp128 import ESPHomeTransport


class _SensorState:
    def __init__(self, key, state):
        self.key = key
        self.state = state


class _NumberState:
    def __init__(self, key, state):
        self.key = key
        self.state = state


class _FakeClient:
    instances = []
    subscribe_calls = 0
    remove_calls = 0
    fail_subscribe = False
    emit_initial = True

    def __init__(self, *args, **kwargs):
        self.callbacks = set()
        self.connected = False
        self.disconnected = False
        type(self).instances.append(self)

    async def connect(self, login=True):
        self.connected = True

    async def list_entities_services(self):
        entities = [
            SimpleNamespace(key=1, object_id="rd_voltage", device_id=1),
            SimpleNamespace(key=2, object_id="rd_current", device_id=1),
            SimpleNamespace(key=3, object_id="rd_output", device_id=1),
            SimpleNamespace(key=4, object_id="rd_set_voltage", device_id=1),
        ]
        return entities, []

    def subscribe_states(self, callback):
        type(self).subscribe_calls += 1
        if type(self).fail_subscribe:
            raise RuntimeError("subscription failed")
        self.callbacks.add(callback)
        if type(self).emit_initial:
            callback(_SensorState(1, 12.7))
            callback(_SensorState(2, 0.0))
            callback(_SensorState(3, 0.0))
            callback(_NumberState(4, 14.7))

        def remove():
            type(self).remove_calls += 1
            self.callbacks.discard(callback)

        return remove

    async def disconnect(self):
        self.disconnected = True

    def handler_count(self):
        return len(self.callbacks)


def _config():
    return PhysicalTransportConfig(
        name="esp128",
        type="esphome",
        enabled=True,
        priority=1,
        connection=ConnectionConfig("127.0.0.1", 6053, key_env="ESPHOME_API_KEY"),
        entities={
            "voltage": "rd_voltage",
            "current": "rd_current",
            "output_state": "rd_output",
            "configured_voltage": "rd_set_voltage",
        },
    )


class ESPHomeTransportSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeClient.instances.clear()
        _FakeClient.subscribe_calls = 0
        _FakeClient.remove_calls = 0
        _FakeClient.fail_subscribe = False
        _FakeClient.emit_initial = True

    async def asyncSetUp(self):
        async def no_sleep(_seconds):
            return None

        self.sleep_patch = patch("runtime.physical.transports.esp128.asyncio.sleep", new=no_sleep)
        self.sleep_patch.start()
        self.client_patch = patch("runtime.physical.transports.esp128.APIClient", _FakeClient)
        self.client_patch.start()
        self.env_patch = patch.dict(os.environ, {"ESPHOME_API_KEY": "test-key"})
        self.env_patch.start()

    async def asyncTearDown(self):
        self.client_patch.stop()
        self.sleep_patch.stop()
        self.env_patch.stop()

    async def test_first_read_registers_one_subscription_and_reads_cache(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        live = await transport.get_live_values()
        self.assertEqual(_FakeClient.subscribe_calls, 1)
        self.assertEqual(live["voltage"], 12.7)
        self.assertEqual(live["configured_voltage"], 14.7)
        await transport.close()

    async def test_repeated_reads_do_not_accumulate_handlers(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        for _ in range(100):
            await transport.get_live_values()
        self.assertEqual(_FakeClient.subscribe_calls, 1)
        self.assertEqual(_FakeClient.instances[0].handler_count(), 1)
        await transport.close()

    async def test_callback_updates_latest_value_only(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport.get_live_values()
        client = _FakeClient.instances[0]
        client.callbacks.copy().pop()(_SensorState(1, 13.1))
        live = await transport.get_live_values()
        self.assertEqual(live["voltage"], 13.1)
        self.assertEqual(len(transport._state_cache["rd_voltage"]), 1)
        await transport.close()

    async def test_concurrent_reads_still_use_one_subscription(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await asyncio.gather(*(transport.get_live_values() for _ in range(20)))
        self.assertEqual(_FakeClient.subscribe_calls, 1)
        self.assertEqual(_FakeClient.instances[0].handler_count(), 1)
        await transport.close()

    async def test_close_removes_subscription_and_next_connection_recreates_one(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport.get_live_values()
        await transport.close()
        self.assertEqual(_FakeClient.remove_calls, 1)
        self.assertEqual(transport._state_cache, {})
        await transport.get_live_values()
        self.assertEqual(_FakeClient.subscribe_calls, 2)
        self.assertEqual(_FakeClient.remove_calls, 1)
        await transport.close()
        self.assertEqual(_FakeClient.remove_calls, 2)

    async def test_subscription_failure_does_not_leave_partial_state(self):
        _FakeClient.fail_subscribe = True
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        with self.assertRaisesRegex(RuntimeError, "subscription failed"):
            await transport.get_live_values()
        self.assertIsNone(transport._state_subscription_remover)
        self.assertEqual(transport._state_cache, {})
        await transport.close()

    async def test_missing_initial_state_remains_unknown(self):
        _FakeClient.emit_initial = False
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        live = await transport.get_live_values()
        self.assertIsNone(live["voltage"])
        self.assertEqual(live["_meta"]["voltage"]["status"], "unknown")
        await transport.close()


if __name__ == "__main__":
    unittest.main()
