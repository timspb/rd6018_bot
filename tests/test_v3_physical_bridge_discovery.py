import unittest

from runtime.output.bridge import HardwareCapability, HardwareSnapshot, PhysicalBridgeAdapter, validate_readback
from hardware_mapping_fixtures import capability_from_mapping, snapshot_from_mapping


class V3PhysicalBridgeDiscoveryTests(unittest.TestCase):
    def test_capability_snapshot_and_limits(self):
        capability = HardwareCapability(True, True, 0.0 + 0.1, 18.0, 0.01, 0.1, 12.0, 0.01, True, True, True, True, True, True)
        self.assertTrue(capability.supports_output_state_readback)
        mapped = capability_from_mapping(capability.__dict__)
        self.assertEqual(mapped.max_voltage, 18.0)

    def test_snapshot_readback_report_only(self):
        snapshot = HardwareSnapshot(100.0, "connected", True, 14.0, 2.5, 14.4, 2.0, 15.0, 3.0)
        result = validate_readback(snapshot, expected_output=True)
        self.assertFalse(result.valid)
        self.assertEqual(result.mismatches, ("voltage", "current"))

    def test_missing_snapshot_fields_are_not_commands(self):
        snapshot = snapshot_from_mapping({"timestamp": 1.0, "connection_state": "missing"})
        self.assertIsNone(snapshot.output_state)
        self.assertTrue(issubclass(PhysicalBridgeAdapter, object))

    def test_invalid_capability_rejected(self):
        with self.assertRaises(ValueError):
            HardwareCapability(True, True, 10.0, 9.0, 0.1, 0.1, 1.0, 0.1, True, True, True, True, True, True)


if __name__ == "__main__":
    unittest.main()
