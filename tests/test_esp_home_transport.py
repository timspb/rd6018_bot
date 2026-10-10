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


class _ButtonInfo:
    def __init__(self, key, object_id, device_id=1):
        self.key = key
        self.object_id = object_id
        self.device_id = device_id


class _FakeClient:
    instances = []
    subscribe_calls = 0
    remove_calls = 0
    fail_subscribe = False
    emit_initial = True
    return_remover = True
    connected_state = True

    def __init__(self, *args, **kwargs):
        self.callbacks = set()
        self.connected = False
        self.disconnected = False
        self.closed_callbacks = set()
        self.button_commands = []
        type(self).instances.append(self)

    async def connect(self, login=True):
        self.connected = True

    @property
    def is_connected(self):
        return type(self).connected_state and self.connected and not self.disconnected

    def add_connection_closed_callback(self, callback):
        self.closed_callbacks.add(callback)

        def remove():
            self.closed_callbacks.discard(callback)

        return remove

    async def list_entities_services(self):
        entities = [
            SimpleNamespace(key=1, object_id="rd_voltage", device_id=1),
            SimpleNamespace(key=2, object_id="rd_current", device_id=1),
            SimpleNamespace(key=3, object_id="rd_output", device_id=1),
            SimpleNamespace(key=4, object_id="rd_set_voltage", device_id=1),
            SimpleNamespace(key=10, object_id="safety_lease_armed", device_id=0),
            SimpleNamespace(key=11, object_id="safety_lease_tripped", device_id=0),
            SimpleNamespace(key=12, object_id="safety_boot_quarantine", device_id=0),
            SimpleNamespace(key=13, object_id="safety_lease_generation", device_id=0),
            SimpleNamespace(key=14, object_id="safety_modbus_age", device_id=0),
            SimpleNamespace(key=15, object_id="safety_lease_remaining", device_id=0),
            _ButtonInfo(16, "safety_lease_renew", 0),
            _ButtonInfo(17, "safety_lease_disarm", 0),
            _ButtonInfo(18, "safety_lease_release_to_hands_off", 0),
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
            callback(_SensorState(10, 0.0))
            callback(_SensorState(11, 0.0))
            callback(_SensorState(12, 0.0))
            callback(_SensorState(13, 2.0))
            callback(_SensorState(14, 3.0))
            callback(_SensorState(15, 0.0))

        def remove():
            type(self).remove_calls += 1
            self.callbacks.discard(callback)

        return remove if type(self).return_remover else None

    async def disconnect(self):
        self.disconnected = True

    def handler_count(self):
        return len(self.callbacks)

    def button_command(self, key, device_id):
        self.button_commands.append((key, device_id))


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
        edge_entities={
            "edge_lease_renew": "safety_lease_renew",
            "edge_lease_disarm": "safety_lease_disarm",
            "edge_lease_release_to_hands_off": "safety_lease_release_to_hands_off",
            "edge_lease_armed": "safety_lease_armed",
            "edge_lease_tripped": "safety_lease_tripped",
            "edge_boot_quarantine": "safety_boot_quarantine",
            "edge_lease_generation": "safety_lease_generation",
            "edge_modbus_age": "safety_modbus_age",
            "edge_lease_remaining": "safety_lease_remaining",
        },
    )


class ESPHomeTransportSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeClient.instances.clear()
        _FakeClient.subscribe_calls = 0
        _FakeClient.remove_calls = 0
        _FakeClient.fail_subscribe = False
        _FakeClient.emit_initial = True
        _FakeClient.return_remover = True
        _FakeClient.connected_state = True

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

    async def test_api_without_remover_is_bounded_by_connection_lifecycle(self):
        _FakeClient.return_remover = False
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        for _ in range(100):
            await transport.get_live_values()
        self.assertEqual(_FakeClient.subscribe_calls, 1)
        self.assertEqual(_FakeClient.instances[0].handler_count(), 1)
        await transport.close()
        self.assertTrue(_FakeClient.instances[0].disconnected)

    async def test_missing_initial_state_remains_unknown(self):
        _FakeClient.emit_initial = False
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        live = await transport.get_live_values()
        self.assertIsNone(live["voltage"])
        self.assertEqual(live["_meta"]["voltage"]["status"], "unknown")
        await transport.close()

    async def test_native_edge_readback_returns_all_six_states_with_age_and_type(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        for entity_id in (
            "binary_sensor.rd6018_rd_6018_safety_lease_armed",
            "binary_sensor.rd6018_rd_6018_safety_lease_tripped",
            "binary_sensor.rd6018_rd_6018_safety_boot_quarantine",
            "sensor.rd6018_rd_6018_safety_lease_generation",
            "sensor.rd6018_rd_6018_safety_modbus_age",
            "sensor.rd6018_rd_6018_safety_lease_remaining",
        ):
            value, attrs = await transport.get_entity_state(entity_id)
            self.assertIsNotNone(value)
            self.assertEqual(attrs["source"], "esp_native_api")
            self.assertLessEqual(attrs["age_s"], 20.0)
        await transport.close()

    async def test_native_missing_edge_entity_is_fail_closed(self):
        config = _config()
        config = PhysicalTransportConfig(
            config.name, config.type, config.enabled, config.priority,
            config.connection, config.entities,
            {**config.edge_entities, "edge_lease_armed": "not_present"},
        )
        transport = ESPHomeTransport(config, RDConfig(60.0, 18.0, 1000.0))
        value, attrs = await transport.get_entity_state(
            "binary_sensor.rd6018_rd_6018_safety_lease_armed"
        )
        self.assertIsNone(value)
        self.assertEqual(attrs["status"], "missing")
        await transport.close()

    async def test_native_button_path_does_not_use_home_assistant(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport.discover()
        self.assertTrue(await transport.press_button(
            "button.rd6018_rd_6018_safety_lease_renew"
        ))
        self.assertEqual(_FakeClient.instances[0].button_commands, [(16, 0)])
        await transport.close()

    async def test_reconnects_when_cached_client_reports_disconnected(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport.get_live_values()
        first = _FakeClient.instances[0]
        type(first).connected_state = False
        await transport.get_live_values()
        self.assertEqual(len(_FakeClient.instances), 2)
        self.assertTrue(first.disconnected)
        await transport.close()


if __name__ == "__main__":
    unittest.main()
