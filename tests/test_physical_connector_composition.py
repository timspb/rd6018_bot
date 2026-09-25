import unittest
import os
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
