"""Native ESPHome switch/binary diagnostics are not NumberInfo streams."""
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from runtime.config.models import RDConfig
from runtime.physical.transports.esp128 import ESPHomeTransport
from tests.test_esp_home_transport import (
    _config, _FakeClient, SwitchInfo, SwitchState,
    BinarySensorInfo, BinarySensorState,
)


class NativeStatusTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_switch_and_status_binaries_are_read_with_native_types(self):
        config = _config()
        config = replace(config, entities={
            **config.entities,
            "control_output": "rd_switch_output",
            "take_ok": "take_ok_v2",
            "take_out": "take_out_v2",
            "boot_power": "boot_power_v2",
        })
        original_entities = _FakeClient.list_entities_services
        original_subscribe = _FakeClient.subscribe_states

        async def entities(client):
            listed, services = await original_entities(client)
            return [*listed,
                    SwitchInfo(20, "rd_switch_output"),
                    BinarySensorInfo(21, "take_ok_v2"),
                    BinarySensorInfo(22, "take_out_v2"),
                    BinarySensorInfo(23, "boot_power_v2")], services

        def subscription(client, callback):
            remover = original_subscribe(client, callback)
            callback(SwitchState(20, True))
            callback(BinarySensorState(21, True))
            callback(BinarySensorState(22, False))
            callback(BinarySensorState(23, False))
            return remover

        async def no_sleep(_):
            return None

        with patch("runtime.physical.transports.esp128.APIClient", _FakeClient), \
             patch("runtime.physical.transports.esp128.asyncio.sleep", new=no_sleep), \
             patch.object(_FakeClient, "list_entities_services", new=entities), \
             patch.object(_FakeClient, "subscribe_states", new=subscription), \
             patch.dict(os.environ, {"ESPHOME_API_KEY": "mock-test-key"}):
            transport = ESPHomeTransport(config, RDConfig(60., 18., 1000.))
            try:
                live = await transport.get_live_values()
                for key, value, kind in (
                    ("control_output", True, "SwitchState"),
                    ("take_ok", True, "BinarySensorState"),
                    ("take_out", False, "BinarySensorState"),
                    ("boot_power", False, "BinarySensorState"),
                ):
                    with self.subTest(key=key):
                        self.assertIs(live[key], value)
                        self.assertEqual(live["_meta"][key]["status"], "ok")
                        self.assertEqual(live["_meta"][key]["native_type"], kind)
                        self.assertEqual(live["_meta"][key]["source"], "esp_native_api")
                self.assertEqual(live["output_state_code_v2"], 0.0)
                self.assertEqual(live["switch"], "off")
            finally:
                await transport.close()

    async def test_absent_optional_flags_stay_unknown_not_false(self):
        config = replace(_config(), entities={
            **_config().entities,
            "take_ok": "missing_take_ok",
            "take_out": "missing_take_out",
            "boot_power": "missing_boot_power",
        })
        async def no_sleep(_):
            return None
        with patch("runtime.physical.transports.esp128.APIClient", _FakeClient), \
             patch("runtime.physical.transports.esp128.asyncio.sleep", new=no_sleep), \
             patch.dict(os.environ, {"ESPHOME_API_KEY": "mock-test-key"}):
            transport = ESPHomeTransport(config, RDConfig(60., 18., 1000.))
            try:
                live = await transport.get_live_values()
                for key in ("take_ok", "take_out", "boot_power"):
                    self.assertIsNone(live[key])
                    self.assertEqual(live["_meta"][key]["status"], "unknown")
            finally:
                await transport.close()
