import unittest

from tools.b1027_native_setpoint_evidence import EvidenceError, validate_programmed_setpoints


OBJECT_IDS = {
    "configured_voltage": "set_voltage_readback_v2",
    "configured_current": "set_current_readback_v2",
}


def receipt():
    return {
        "request_id": "captured-write-1",
        "write_completed_monotonic": 10.0,
        "connection_generation": 4,
        "set_voltage_v": 14.4,
        "set_current_a": 3.2,
        "baseline_voltage_monotonic": 9.0,
        "baseline_current_monotonic": 9.2,
    }


def native(*, voltage_meta=None, current_meta=None):
    base = {
        "source": "esp_native_api",
        "status": "ok",
        "native_type": "SensorState",
        "object_id": OBJECT_IDS["configured_voltage"],
        "device_id": 128,
        "connection_generation": 4,
        "subscription_timestamp_monotonic": 10.2,
        "age_s": 0.3,
        "key": 8,
    }
    vmeta = dict(base)
    imeta = dict(base, object_id=OBJECT_IDS["configured_current"], key=9,
                 subscription_timestamp_monotonic=10.3)
    if voltage_meta:
        vmeta.update(voltage_meta)
    if current_meta:
        imeta.update(current_meta)
    return {
        "configured_voltage": {"value": 14.4, "meta": vmeta},
        "configured_current": {"value": 3.2, "meta": imeta},
    }


def validate(*, receipt_value=None, native_value=None):
    return validate_programmed_setpoints(
        receipt=receipt_value or receipt(),
        native=native_value or native(),
        expected_object_ids=OBJECT_IDS,
        now_monotonic=10.5,
        voltage_tolerance_v=0.06,
        current_tolerance_a=0.06,
        voltage_range_v=(0.0, 17.5),
        current_range_a=(0.0, 12.0),
        max_age_s=8.0,
    )


class B1027NativeSetpointEvidenceTests(unittest.TestCase):
    def test_accepts_captured_same_device_post_write_native_sensor_states(self):
        result = validate()
        self.assertEqual(result["status"], "SOURCE_EVIDENCE_VALIDATED")
        self.assertEqual(result["device_id"], 128)
        self.assertEqual(result["connection_generation"], 4)

    def test_rejects_stale_ha_only_and_wrong_native_type(self):
        cases = (
            {"age_s": 8.1},
            {"source": "ha102_rest"},
            {"native_type": "NumberState"},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(EvidenceError):
                validate(native_value=native(voltage_meta=change))

    def test_rejects_wrong_configured_object_identity(self):
        with self.assertRaisesRegex(EvidenceError, "identity"):
            validate(native_value=native(voltage_meta={"object_id": "output_voltage"}))

    def test_rejects_device_and_connection_generation_mismatch(self):
        for change in ({"device_id": 129}, {"connection_generation": 5}):
            with self.subTest(change=change), self.assertRaises(EvidenceError):
                validate(native_value=native(current_meta=change))

    def test_rejects_pre_write_sample_and_identical_old_heartbeat(self):
        old = {"subscription_timestamp_monotonic": 9.0}
        with self.assertRaisesRegex(EvidenceError, "did not advance"):
            validate(native_value=native(voltage_meta=old))
        with self.assertRaisesRegex(EvidenceError, "did not advance"):
            validate(native_value=native(current_meta={"subscription_timestamp_monotonic": 10.0}))

    def test_rejects_impossible_values_and_receipt_without_real_completion(self):
        with self.assertRaisesRegex(EvidenceError, "physical range"):
            validate(native_value=native(voltage_meta={"subscription_timestamp_monotonic": 10.2}) | {
                "configured_voltage": {"value": 99.0, "meta": native()["configured_voltage"]["meta"]}
            })
        missing_time = receipt()
        del missing_time["write_completed_monotonic"]
        with self.assertRaisesRegex(EvidenceError, "receipt"):
            validate(receipt_value=missing_time)


if __name__ == "__main__":
    unittest.main()
