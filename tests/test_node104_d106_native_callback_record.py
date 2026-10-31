"""D106 measured values retain keyed SensorState identity across cache collisions."""
import unittest
from tools.node104_d106_live_observer import _native_callback_record, ro


class D106NativeCallbackRecordTests(unittest.TestCase):
    def setUp(self):
        self.sensor = type("SensorInfo", (), {})()
        self.sensor.object_id, self.sensor.key, self.sensor.device_id = "output_voltage", 2, 0
        self.colliding_number = type("NumberInfo", (), {})()
        self.colliding_number.object_id, self.colliding_number.key, self.colliding_number.device_id = "output_voltage", 20, 0
        self.inventory = (self.sensor, self.colliding_number)
        self.meta = {
            "source": "esp_native_api", "object_id": "output_voltage",
            "status": "ok", "native_type": "SensorState",
            "entity_type": "SensorInfo", "age_s": 0.4,
            "subscription_timestamp_monotonic": 100.0,
            "key": 2, "device_id": 0,
        }

    def test_uses_fresh_sensor_callback_when_number_info_shares_object_id(self):
        result = _native_callback_record("voltage_v", (0.0, self.meta),
                                         self.inventory, 200.0)
        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["meta"]["actual_object_id"], "output_voltage")
        self.assertEqual(result["meta"]["native_key"], 2)
        self.assertEqual(result["meta"]["native_type"], "SensorState")
        self.assertEqual(result["meta"]["device_id"], 0)

    def test_rejects_stale_or_wrong_typed_callback(self):
        for changes in ({"age_s": 9.0}, {"native_type": "NumberState"}):
            bad = dict(self.meta, **changes)
            with self.subTest(changes=changes), self.assertRaises(ro.ProofError):
                _native_callback_record("voltage_v", (0.0, bad), self.inventory, 200.0)

    def test_rejects_callback_key_or_device_that_does_not_match_inventory(self):
        for changes in ({"key": 20}, {"device_id": 9}):
            bad = dict(self.meta, **changes)
            with self.subTest(changes=changes), self.assertRaises(ro.ProofError):
                _native_callback_record("voltage_v", (0.0, bad), self.inventory, 200.0)


if __name__ == "__main__":
    unittest.main()