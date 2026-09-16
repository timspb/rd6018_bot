import unittest
from pathlib import Path

from runtime.config import load_config
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.transports import (
    ESPHomeTransport, HA102Transport, PhysicalSnapshotComparator,
    PhysicalTransportFactory,
)


class V3MultiTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(Path("config"))

    def test_factory_uses_configured_profiles(self):
        factory = PhysicalTransportFactory(self.config)
        self.assertIsInstance(factory.create("ha102"), HA102Transport)
        self.assertIsInstance(factory.create("esp128"), ESPHomeTransport)

    def test_transport_profiles_are_read_only(self):
        for name in ("ha102", "esp128"):
            transport = PhysicalTransportFactory(self.config).create(name)
            self.assertTrue(transport.config.entities)
            self.assertIsNone(getattr(transport, "set_voltage", None))
            self.assertIsNone(getattr(transport, "enable", None))

    def test_snapshot_comparison(self):
        left = HardwareSnapshot(1, "connected", False, 12.1, .2, 14.4, 2.0, 15.0, 2.1)
        right = HardwareSnapshot(2, "connected", False, 12.12, .21, 14.4, 2.0, 15.0, 2.1)
        self.assertEqual(PhysicalSnapshotComparator.compare(left, right).status, "MATCH")
        changed = HardwareSnapshot(2, "connected", True, 12.12, .21, 14.4, 2.0, 15.0, 2.1)
        self.assertEqual(PhysicalSnapshotComparator.compare(left, changed).status, "MISMATCH")
        self.assertEqual(PhysicalSnapshotComparator.compare(left, None).status, "INCONCLUSIVE")

    def test_config_contains_no_secret_values(self):
        for path in Path("config/physical").glob("*.yaml"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("Bearer", content)
            self.assertNotIn("password:", content)
