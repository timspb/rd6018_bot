import asyncio
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.config.models import ConnectionConfig, PhysicalTransportConfig, RDConfig
from runtime.physical.transports.esp128 import ESPHomeTransport


class _SensorState:
    def __init__(self, key, state):
        self.key = key
        self.state = state


class SensorState(_SensorState):
    pass


class BinarySensorState(_SensorState):
    pass


class SensorInfo:
    def __init__(self, key, object_id, device_id=1):
        self.key, self.object_id, self.device_id = key, object_id, device_id


class BinarySensorInfo(SensorInfo):
    pass


class _NumberState:
    def __init__(self, key, state):
        self.key = key
        self.state = state


class NumberState(_NumberState):
    pass


class NumberInfo:
    def __init__(self, key, object_id, device_id=1):
        self.key, self.object_id, self.device_id = key, object_id, device_id


class _ButtonInfo:
    def __init__(self, key, object_id, device_id=1):
        self.key = key
        self.object_id = object_id
        self.device_id = device_id


class ButtonInfo(_ButtonInfo):
    pass


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
            SensorInfo(1, "rd_voltage"),
            SensorInfo(2, "rd_current"),
            SensorInfo(3, "rd_output"),
            NumberInfo(4, "rd_set_voltage"),
            BinarySensorInfo(10, "safety_lease_armed", 0),
            BinarySensorInfo(11, "safety_lease_tripped", 0),
            BinarySensorInfo(12, "safety_boot_quarantine", 0),
            SensorInfo(13, "safety_lease_generation", 0),
            SensorInfo(14, "safety_modbus_age", 0),
            SensorInfo(15, "safety_lease_remaining", 0),
            ButtonInfo(16, "safety_lease_renew", 0),
            ButtonInfo(17, "safety_lease_disarm", 0),
            ButtonInfo(18, "safety_lease_release_to_hands_off", 0),
            ButtonInfo(19, "safety_lease_adopt_live_output", 0),
        ]
        return entities, []

    def subscribe_states(self, callback):
        type(self).subscribe_calls += 1
        if type(self).fail_subscribe:
            raise RuntimeError("subscription failed")
        self.callbacks.add(callback)
        if type(self).emit_initial:
            callback(SensorState(1, 12.7))
            callback(SensorState(2, 0.0))
            callback(SensorState(3, 0.0))
            callback(NumberState(4, 14.7))
            callback(BinarySensorState(10, False))
            callback(BinarySensorState(11, False))
            callback(BinarySensorState(12, False))
            callback(SensorState(13, 2.0))
            callback(SensorState(14, 3.0))
            callback(SensorState(15, 0.0))

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
            "edge_lease_adopt_live_output": "safety_lease_adopt_live_output",
            "edge_lease_armed": "safety_lease_armed",
            "edge_lease_tripped": "safety_lease_tripped",
            "edge_boot_quarantine": "safety_boot_quarantine",
            "edge_lease_generation": "safety_lease_generation",
            "edge_modbus_age": "safety_modbus_age",
            "edge_lease_remaining": "safety_lease_remaining",
            "edge_lease_ttl": "safety_lease_ttl",
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

    async def test_output_heartbeat_is_native_callback_not_cache_fetch_time(self):
        import time
        from runtime_safety import RuntimeSafetyGuard

        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        first = await transport.get_live_values()
        source = first["_meta"]["output_state_code_v2"]
        self.assertEqual(source["status"], "ok")
        self.assertEqual(source["source_key"], "output_state_code_v2")
        self.assertEqual(source["last_reported"], first["_meta"]["switch"]["last_reported"])
        self.assertLess(source["age_s"], 8.0)

        # A cache read alone is NOT a new sensor heartbeat.
        guard = RuntimeSafetyGuard.__new__(RuntimeSafetyGuard)
        before = guard._output_evidence(first)
        command_epoch = time.time()
        repeated = await transport.get_live_values()
        unchanged = guard._output_evidence(repeated)
        self.assertEqual(before.heartbeat_epoch, unchanged.heartbeat_epoch)
        self.assertFalse(guard._is_post_command(unchanged, before, command_epoch))

        # Only the actual native SensorState callback advances the heartbeat.
        transport._on_state(SensorState(3, 0.0))
        updated = guard._output_evidence(await transport.get_live_values())
        self.assertGreater(updated.heartbeat_epoch, before.heartbeat_epoch)
        self.assertTrue(guard._is_post_command(updated, before, command_epoch))
        await transport.close()

    async def test_stale_native_output_age_not_advertised_fresh(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport.get_live_values()
        transport._state_updated_at[("SensorInfo", 3)] -= 30.0
        live = await transport.get_live_values()
        self.assertGreaterEqual(live["_meta"]["output_state_code_v2"]["age_s"], 30.0)
        self.assertEqual(live["_meta"]["output_state_code_v2"]["last_reported"],
                         live["_meta"]["switch"]["last_reported"])
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
        client.callbacks.copy().pop()(SensorState(1, 13.1))
        live = await transport.get_live_values()
        self.assertEqual(live["voltage"], 13.1)
        self.assertEqual(len(transport._state_cache[("SensorInfo", 1)]), 1)
        await transport.close()

    async def test_same_object_id_sensor_and_number_keep_independent_typed_cache_for_d106(self):
        config = _config()
        config.entities["configured_voltage"] = "rd_voltage"
        original = _FakeClient.list_entities_services

        async def colliding_inventory(client):
            entities, services = await original(client)
            entities.extend((NumberInfo(20, "rd_voltage"),))
            return entities, services

        def colliding_subscription(self, callback):
            type(self).subscribe_calls += 1
            self.callbacks.add(callback)
            callback(SensorState(1, 0.0))
            callback(NumberState(20, 14.72))
            callback(SensorState(2, 0.0))
            callback(SensorState(3, 0.0))
            for key in (10, 11, 12):
                callback(BinarySensorState(key, False))
            for key in (13, 14, 15):
                callback(SensorState(key, 0.0))
            return lambda: self.callbacks.discard(callback)

        with patch.object(_FakeClient, "list_entities_services", colliding_inventory), \
                patch.object(_FakeClient, "subscribe_states", colliding_subscription):
            transport = ESPHomeTransport(config, RDConfig(60.0, 18.0, 1000.0))
            live = await transport.get_live_values()
            self.assertEqual(live["voltage"], 0.0)
            self.assertEqual(live["configured_voltage"], 14.72)
            self.assertEqual(live["_meta"]["voltage"]["native_type"], "SensorState")
            self.assertEqual(live["_meta"]["configured_voltage"]["native_type"], "NumberState")
            self.assertEqual(live["_meta"]["voltage"]["key"], 1)
            self.assertEqual(live["_meta"]["configured_voltage"]["key"], 20)
            measured_state, measured_meta = await transport.get_entity_state("sensor.rd_voltage")
            setpoint_state, setpoint_meta = await transport.get_entity_state("number.rd_voltage")
            self.assertEqual((measured_state, measured_meta["key"]), (0.0, 1))
            self.assertEqual((setpoint_state, setpoint_meta["key"]), (14.72, 20))

            # D106's normal native record helper must identify SensorInfo from
            # the colliding inventory by type and key, not reject both entries.
            from tools import node104_d106_live_observer as d106
            measured = d106._native_record("voltage_v", "rd_voltage", transport,
                                           tuple(transport.entities), time.time())
            self.assertEqual(measured["value"], 0.0)
            self.assertEqual(measured["meta"]["entity_type"], "SensorInfo")
            self.assertEqual(measured["meta"]["native_key"], 1)
            setpoint = d106._native_record("set_voltage_v", "rd_voltage", transport,
                                          tuple(transport.entities), time.time())
            self.assertEqual(setpoint["value"], 14.72)
            self.assertEqual(setpoint["meta"]["entity_type"], "NumberInfo")
            self.assertEqual(setpoint["meta"]["native_key"], 20)
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

    async def test_physical_output_report_uses_configured_sensor_not_edge_whitelist(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        value, attrs = await transport.get_physical_output_report()
        self.assertEqual(value, 0.0)
        self.assertEqual(attrs["native_type"], "SensorState")
        self.assertIsInstance(attrs["subscription_timestamp_monotonic"], float)
        self.assertLessEqual(attrs["age_s"], 8.0)
        edge_value, edge_attrs = await transport.get_entity_state("sensor.arbitrary_native_output")
        self.assertIsNone(edge_value)
        self.assertEqual(edge_attrs["status"], "missing")
        await transport.close()

    async def test_native_read_resolution_is_config_whitelisted_and_button_write_stays_edge_only(self):
        config = _config()
        config.entities.update({
            "autonomous_mode": "safety_autonomous_mode",
            "protection_code": "protection_status_code",
        })
        transport = ESPHomeTransport(config, RDConfig(60.0, 18.0, 1000.0))
        self.assertEqual(transport._read_object_id(
            "binary_sensor.rd6018_safety_autonomous_mode"), "safety_autonomous_mode")
        value, attrs = await transport.get_entity_state("sensor.unconfigured_native_object")
        self.assertIsNone(value)
        self.assertEqual(attrs["status"], "missing")
        # Ordinary configured read mappings must not become write authority.
        self.assertIsNone(transport._edge_object_id("button.safety_autonomous_mode"))
        with self.assertRaisesRegex(RuntimeError, "not available"):
            await transport.press_button("button.safety_autonomous_mode")
        self.assertEqual(_FakeClient.instances[0].button_commands, [])
        await transport.close()

    async def test_physical_output_report_fails_closed_for_unknown_stale_and_wrong_type(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        _FakeClient.emit_initial = False
        value, attrs = await transport.get_physical_output_report()
        self.assertIsNone(value)
        self.assertEqual(attrs["status"], "unknown")
        await transport.close()

        _FakeClient.emit_initial = True
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport._ensure_state_subscription()
        transport._state_updated_at[("SensorInfo", 3)] -= 9.0
        value, attrs = await transport.get_physical_output_report()
        self.assertIsNone(value)
        self.assertEqual(attrs["status"], "stale")
        self.assertGreater(attrs["age_s"], 8.0)
        await transport.close()

        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport._ensure_state_subscription()
        transport._on_state(_NumberState(3, 0.0))
        value, attrs = await transport.get_physical_output_report()
        self.assertEqual(value, 0.0)
        self.assertEqual(attrs["native_type"], "SensorState")
        transport._on_state(SensorState(3, 1.0))
        value, attrs = await transport.get_physical_output_report()
        self.assertEqual(value, 1.0)
        self.assertEqual(attrs["native_type"], "SensorState")
        await transport.close()

    async def test_physical_output_report_rejects_non_binary_sensor_values(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport._ensure_state_subscription()
        transport._on_state(SensorState(3, 2.0))
        value, attrs = await transport.get_physical_output_report()
        self.assertIsNone(value)
        self.assertEqual(attrs["status"], "invalid_value")
        await transport.close()

    async def test_native_button_path_does_not_use_home_assistant(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        await transport.discover()
        self.assertTrue(await transport.press_button(
            "button.rd6018_rd_6018_safety_lease_renew"
        ))
        self.assertEqual(_FakeClient.instances[0].button_commands, [(16, 0)])
        await transport.close()

    async def test_button_inventory_is_read_only_and_restricted_to_configured_button(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        info = await transport.get_button_info(
            "button.rd6018_rd_6018_safety_lease_release_to_hands_off"
        )
        self.assertEqual(info["status"], "ok")
        self.assertEqual(info["native_type"], "ButtonInfo")
        self.assertEqual(info["key"], 18)
        self.assertEqual(_FakeClient.instances[0].button_commands, [])
        missing = await transport.get_button_info("button.arbitrary_button")
        self.assertEqual(missing["status"], "missing")
        await transport.close()

    async def test_native_autonomous_buttons_use_explicit_recipe_and_buttoninfo(self):
        from pathlib import Path
        import yaml
        recipe = yaml.safe_load(Path("config/physical/esp128.yaml").read_text())
        self.assertEqual(recipe["edge_entities"]["edge_autonomous_enter"], "safety_enter_autonomous")
        self.assertEqual(recipe["edge_entities"]["edge_autonomous_exit"], "safety_exit_autonomous")
        config = _config()
        config.edge_entities.update({
            "edge_autonomous_enter": "safety_enter_autonomous",
            "edge_autonomous_exit": "safety_exit_autonomous",
        })
        original = _FakeClient.list_entities_services

        async def with_autonomous(client):
            entities, services = await original(client)
            entities.extend([ButtonInfo(20, "safety_enter_autonomous", 0),
                             ButtonInfo(21, "safety_exit_autonomous", 0)])
            return entities, services

        with patch.object(_FakeClient, "list_entities_services", with_autonomous):
            transport = ESPHomeTransport(config, RDConfig(60.0, 18.0, 1000.0))
            enter = "button.rd6018_rd_6018_safety_enter_autonomous"
            exit_ = "button.rd6018_rd_6018_safety_exit_autonomous"
            self.assertEqual((await transport.get_button_info(enter))["native_type"], "ButtonInfo")
            self.assertEqual((await transport.get_button_info(exit_))["native_type"], "ButtonInfo")
            self.assertTrue(await transport.press_button(enter))
            self.assertTrue(await transport.press_button(exit_))
            self.assertEqual(_FakeClient.instances[0].button_commands, [(20, 0), (21, 0)])
            await transport.close()

    async def test_autonomous_button_without_recipe_mapping_fails_closed(self):
        original = _FakeClient.list_entities_services

        async def with_autonomous(client):
            entities, services = await original(client)
            entities.append(ButtonInfo(20, "safety_enter_autonomous", 0))
            return entities, services

        with patch.object(_FakeClient, "list_entities_services", with_autonomous):
            transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
            button = "button.rd6018_rd_6018_safety_enter_autonomous"
            self.assertEqual((await transport.get_button_info(button))["status"], "missing")
            with self.assertRaisesRegex(RuntimeError, "not available"):
                await transport.press_button(button)
            self.assertEqual(_FakeClient.instances[0].button_commands, [])
            await transport.close()

    async def test_live_adoption_button_requires_explicit_mapping_and_uses_native_inventory(self):
        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        entity_id = "button.rd6018_rd_6018_safety_lease_adopt_live_output"
        info = await transport.get_button_info(entity_id)
        self.assertEqual(info["status"], "ok")
        self.assertEqual(info["native_type"], "ButtonInfo")
        self.assertEqual(info["object_id"], "safety_lease_adopt_live_output")
        self.assertEqual(info["key"], 19)
        self.assertEqual(_FakeClient.instances[0].button_commands, [])
        self.assertTrue(await transport.press_button(entity_id))
        self.assertEqual(_FakeClient.instances[0].button_commands, [(19, 0)])
        await transport.close()

    async def test_live_adoption_button_missing_mapping_or_wrong_native_type_fails_closed(self):
        config = _config()
        config.edge_entities.pop("edge_lease_adopt_live_output")
        transport = ESPHomeTransport(config, RDConfig(60.0, 18.0, 1000.0))
        missing = await transport.get_button_info(
            "button.rd6018_rd_6018_safety_lease_adopt_live_output")
        self.assertEqual(missing["status"], "missing")
        await transport.close()

        transport = ESPHomeTransport(_config(), RDConfig(60.0, 18.0, 1000.0))
        original = _FakeClient.list_entities_services

        async def wrong_type(client):
            entities, services = await original(client)
            entities[-1] = SimpleNamespace(key=19,
                object_id="safety_lease_adopt_live_output", device_id=0)
            return entities, services

        with patch.object(_FakeClient, "list_entities_services", wrong_type):
            wrong = await transport.get_button_info(
                "button.rd6018_rd_6018_safety_lease_adopt_live_output")
        self.assertEqual(wrong["status"], "wrong_type")
        self.assertEqual(wrong["native_type"], "SimpleNamespace")
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