import unittest
from unittest.mock import patch

from hass_api import HassClient
from runtime.config import load_config


class PhysicalConnectorCompositionTests(unittest.TestCase):
    def test_config_preserves_existing_connector_selection(self):
        config = load_config("config")
        self.assertEqual(config.default_connector, "esp_direct")

    def test_v2_owner_selects_existing_connector_without_new_owner(self):
        marker = object()
        with patch("runtime.physical.connectors.PhysicalConnectorFactory.create", return_value=marker) as create:
            client = HassClient.from_physical_config()
        create.assert_called_once_with("esp_direct")
        self.assertIs(client._physical_backend, marker)


if __name__ == "__main__":
    unittest.main()
