import unittest

from tools.node104_native_phase_capture import (
    PhaseCaptureError, capture_native_phase,
)
from tools.node104_d106_live_observer import _native_callback_record, ro


class NativePhaseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.inventory = []
        self.records = {}
        for field, oid, key, value in (
            ("output_r18", "output_state", 1, 1),
            ("voltage_v", "output_voltage", 2, 14.2),
            ("current_a", "output_current", 3, 0.8),
        ):
            sensor = type("SensorInfo", (), {})()
            sensor.object_id, sensor.key, sensor.device_id = oid, key, 0
            self.inventory.append(sensor)
            meta = {
                "source": "esp_native_api", "object_id": oid, "status": "ok",
                "native_type": "SensorState", "entity_type": "SensorInfo",
                "age_s": 0.2, "subscription_timestamp_monotonic": 12.0,
                "key": key, "device_id": 0, "connection_generation": 7,
            }
            self.records[field] = _native_callback_record(
                field, (value, meta), tuple(self.inventory), 100.0
            )
        # The first inventory grows as each test record is normalized; rebuild
        # R18 against the complete inventory, as the live observer does.
        self.records["output_r18"] = _native_callback_record(
            "output_r18", (1, {
                "source": "esp_native_api", "object_id": "output_state",
                "status": "ok", "native_type": "SensorState",
                "entity_type": "SensorInfo", "age_s": 0.2,
                "subscription_timestamp_monotonic": 12.0, "key": 1,
                "device_id": 0, "connection_generation": 7,
            }), tuple(self.inventory), 100.0
        )

    def capture(self, records=None, start=10.0, captured=12.5):
        return capture_native_phase(records or self.records,
                                    phase_started_monotonic=start,
                                    captured_at_monotonic=captured)

    def test_projects_native_records_with_original_generation_and_age(self):
        result = self.capture()
        self.assertEqual(result["voltage_v"]["connection_generation"], 7)
        self.assertEqual(result["voltage_v"]["source_key"], 2)
        self.assertEqual(result["voltage_v"]["device_id"], 0)
        self.assertEqual(result["voltage_v"]["age_s"], 0.5)

    def test_rejects_wrong_source_and_missing_generation(self):
        for change in ({"source": "ha102_rest"}, {"connection_generation": None}):
            bad = {key: dict(value, meta=dict(value["meta"]))
                   for key, value in self.records.items()}
            bad["current_a"]["meta"].update(change)
            with self.subTest(change=change), self.assertRaises(PhaseCaptureError):
                self.capture(bad)

    def test_rejects_callbacks_before_phase_or_after_capture(self):
        for timestamp, captured in ((9.9, 12.5), (12.6, 12.5)):
            bad = {key: dict(value, meta=dict(value["meta"]))
                   for key, value in self.records.items()}
            bad["output_r18"]["meta"]["subscription_timestamp_monotonic"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises(PhaseCaptureError):
                self.capture(bad, captured=captured)

    def test_rejects_stale_native_source(self):
        bad = {key: dict(value, meta=dict(value["meta"]))
               for key, value in self.records.items()}
        bad["voltage_v"]["meta"]["subscription_timestamp_monotonic"] = 1.0
        with self.assertRaisesRegex(PhaseCaptureError, "freshness"):
            self.capture(bad)

    def test_rejects_mixed_generations_and_duplicate_sensor_identity(self):
        bad = {key: dict(value, meta=dict(value["meta"]))
               for key, value in self.records.items()}
        bad["current_a"]["meta"]["connection_generation"] = 8
        with self.assertRaisesRegex(PhaseCaptureError, "generations"):
            self.capture(bad)
        bad = {key: dict(value, meta=dict(value["meta"]))
               for key, value in self.records.items()}
        bad["current_a"]["meta"]["device_id"] = 9
        with self.assertRaisesRegex(PhaseCaptureError, "one ESP"):
            self.capture(bad)
        duplicate = type("SensorInfo", (), {})()
        duplicate.object_id, duplicate.key, duplicate.device_id = (
            "output_voltage", 2, 0,
        )
        number = type("NumberInfo", (), {})()
        number.object_id, number.key, number.device_id = "output_voltage", 2, 0
        callback = (14.2, {
            "source": "esp_native_api", "object_id": "output_voltage",
            "status": "ok", "native_type": "SensorState",
            "entity_type": "SensorInfo", "age_s": 0.2,
            "subscription_timestamp_monotonic": 12.0, "key": 2,
            "device_id": 0, "connection_generation": 7,
        })
        with self.assertRaisesRegex(ro.ProofError, "inventory identity"):
            _native_callback_record("voltage_v", callback,
                                    (*self.inventory, number, duplicate), 100.0)


if __name__ == "__main__":
    unittest.main()
