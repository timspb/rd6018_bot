import unittest
import os
from unittest.mock import AsyncMock, patch

from hass_api import HassClient
from runtime.config import load_config


class PhysicalConnectorCompositionTests(unittest.TestCase):
    def test_config_preserves_existing_connector_selection(self):
        with patch.dict(os.environ, {
            "ESPHOME_API_HOST": "127.0.0.1",
            "ESPHOME_API_PORT": "6053",
            "ESPHOME_API_KEY": "test-key",
        }, clear=False):
            config = load_config("config")
        self.assertEqual(config.default_connector, "esp_direct")

    def test_direct_esphome_maps_persistent_autonomous_authority(self):
        with patch.dict(os.environ, {
            "ESPHOME_API_HOST": "127.0.0.1",
            "ESPHOME_API_PORT": "6053",
            "ESPHOME_API_KEY": "test-key",
        }, clear=False):
            config = load_config("config")
        self.assertEqual(
            config.transports["esp128"].entities["autonomous_mode"],
            "safety_autonomous_mode",
        )

    def test_v2_owner_selects_existing_connector_without_new_owner(self):
        marker = object()
        with patch.dict(os.environ, {
            "ESPHOME_API_HOST": "127.0.0.1",
            "ESPHOME_API_PORT": "6053",
            "ESPHOME_API_KEY": "test-key",
        }, clear=False):
            with patch("runtime.physical.connectors.PhysicalConnectorFactory.create", return_value=marker) as create:
                client = HassClient.from_physical_config()
        create.assert_called_once_with("esp_direct")
        self.assertIs(client._physical_backend, marker)

    def test_selected_physical_backend_keeps_ha_rest_sidecar(self):
        class Backend:
            async def get_all_live(self):
                return {"switch": "off", "voltage": 0.0}

        class Response:
            status = 200

            async def json(self):
                return {"state": "on", "attributes": {"friendly_name": "lease"}}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def __init__(self):
                self.requested = []

            def get(self, url):
                self.requested.append(url)
                return Response()

        async def exercise():
            client = HassClient("http://ha.example:8123", "secret", backend=Backend())
            session = Session()
            client._ensure_session = AsyncMock(return_value=session)

            self.assertEqual(("on", {"friendly_name": "lease", "_ha_last_reported": None,
                                     "_ha_last_updated": None, "_ha_last_changed": None}),
                             await client.get_state("binary_sensor.safety_lease_armed"))
            live = await client.get_all_live()
            self.assertEqual("off", live["switch"])
            self.assertEqual(0.0, live["voltage"])
            self.assertEqual(
                ["http://ha.example:8123/api/states/binary_sensor.safety_lease_armed"],
                session.requested,
            )

    def test_native_lease_state_and_button_bypass_ha(self):
        class Backend:
            def __init__(self):
                self.states = []
                self.buttons = []

            async def get_state(self, entity_id):
                self.states.append(entity_id)
                return "off", {"source": "esp_native_api", "age_s": 1.0}

            async def press_button(self, entity_id):
                self.buttons.append(entity_id)
                return True

        import asyncio

        async def exercise():
            backend = Backend()
            client = HassClient("http://ha.example:8123", "secret", backend=backend)
            client._ensure_session = AsyncMock(side_effect=AssertionError("HA must not be used"))
            self.assertEqual(
                ("off", {"source": "esp_native_api", "age_s": 1.0}),
                await client.get_state("binary_sensor.rd6018_rd_6018_safety_lease_armed"),
            )
            self.assertTrue(await client.press_button("button.rd6018_rd_6018_safety_lease_renew"))
            self.assertEqual(backend.states, ["binary_sensor.rd6018_rd_6018_safety_lease_armed"])
            self.assertEqual(backend.buttons, ["button.rd6018_rd_6018_safety_lease_renew"])

        asyncio.run(exercise())

        import asyncio
        asyncio.run(exercise())

    def test_from_physical_config_preserves_ha_sidecar_credentials(self):
        marker = object()
        with patch.dict(os.environ, {
            "ESPHOME_API_HOST": "127.0.0.1",
            "ESPHOME_API_PORT": "6053",
            "ESPHOME_API_KEY": "test-key",
        }, clear=False), patch("hass_api.HA_URL", "http://192.168.1.102:8123"), patch(
            "hass_api.HA_TOKEN", "secret-token"
        ), patch("runtime.physical.connectors.PhysicalConnectorFactory.create", return_value=marker):
            client = HassClient.from_physical_config()

        self.assertEqual("http://192.168.1.102:8123", client.base_url)
        self.assertEqual("secret-token", client.token)
        self.assertIs(client._physical_backend, marker)


if __name__ == "__main__":
    unittest.main()
