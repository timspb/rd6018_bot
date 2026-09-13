import asyncio
import unittest
from dataclasses import replace

from runtime.config import load_config
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.connectors import ConnectorSnapshotComparator, PhysicalConnectorFactory


class IndependentConnectorTests(unittest.TestCase):
    def test_config_and_factory_are_independent(self):
        config = load_config("config")
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
        config = load_config("config")
        ha = PhysicalConnectorFactory(config).create("ha_esp")
        esp = PhysicalConnectorFactory(config).create("esp_direct")
        async def fail():
            ha.transport.health_check = lambda: (_ for _ in ()).throw(RuntimeError("ha down"))
            with self.assertRaises(RuntimeError):
                await ha.health_check()
            esp.transport.health_check = lambda: asyncio.sleep(0, result={"connected": True})
            self.assertTrue((await esp.health_check())["connected"])
        asyncio.run(fail())
