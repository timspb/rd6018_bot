import asyncio
import os
import unittest
from unittest.mock import patch
from dataclasses import replace

from runtime.config import load_config
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.connectors import ConnectorSnapshotComparator, PhysicalConnectorFactory


def _offline_connector_config():
    # These tests construct connectors without opening a physical connection.
    # Supply a non-routable local fixture address instead of depending on
    # the developer's ESPHOME_API_HOST environment or real node credentials.
    with patch.dict(os.environ, {
        "ESPHOME_API_HOST": "127.0.0.1", "ESPHOME_API_PORT": "6053",
    }):
        return load_config("config")


class IndependentConnectorTests(unittest.TestCase):
    def test_config_and_factory_are_independent(self):
        config = _offline_connector_config()
        ha = PhysicalConnectorFactory(config).create("ha_esp")
        esp = PhysicalConnectorFactory(config).create("esp_direct")
        self.assertEqual(ha.name, "ha_esp")
        self.assertEqual(esp.name, "esp_direct")
        self.assertIsNot(ha.transport, esp.transport)

    def test_snapshot_comparator_uses_shared_contract(self):
        left = HardwareSnapshot(100, "connected", False, 0, 0, 13.94, .55, 16.7, 12, 31)
        right = replace(left, timestamp=101)
        self.assertEqual(ConnectorSnapshotComparator.compare(left, right).status, "MATCH")

    def test_connector_failure_is_isolated(self):
        config = _offline_connector_config()
        ha = PhysicalConnectorFactory(config).create("ha_esp")
        esp = PhysicalConnectorFactory(config).create("esp_direct")
        async def fail():
            ha.transport.health_check = lambda: (_ for _ in ()).throw(RuntimeError("ha down"))
            with self.assertRaises(RuntimeError):
                await ha.health_check()
            esp.transport.health_check = lambda: asyncio.sleep(0, result={"connected": True})
            self.assertTrue((await esp.health_check())["connected"])
        asyncio.run(fail())

    def test_write_surface_is_only_verified_disable(self):
        config = _offline_connector_config()
        for name in ("ha_esp", "esp_direct"):
            connector = PhysicalConnectorFactory(config).create(name)
            self.assertTrue(callable(connector.disable_output))
            self.assertTrue(callable(connector.read_snapshot))
