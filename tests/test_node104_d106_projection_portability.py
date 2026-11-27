"""D106 projection safety tests without importing the D090 transaction lifecycle."""
import copy
import time
import unittest

from tools import node104_d106_readonly_projection as projection


class D106ProjectionPortabilityTests(unittest.TestCase):
    def snapshot(self):
        now = time.time()
        fields = {
            "output_r18": 0, "voltage_v": 0.0, "current_a": 0.0,
            "protection_r16": 0, "autonomous": False, "lease_armed": False,
            "lease_remaining_s": 0.0, "lease_ttl_s": 900.0,
            "modbus_age_s": 1.0, "set_voltage_v": 13.57,
            "set_current_a": 0.10,
        }
        raw = {"captured_at_epoch": now, "source_nonces": ["a" * 32, "b" * 32]}
        for name, source in (("ha102", "ha102_rest"), ("esp128", "esp_native_api")):
            raw[name] = {}
            for field, value in fields.items():
                if name == "ha102" and field not in projection.HA_FIELDS:
                    continue
                meta = {"source": source, "object_id": field, "status": "ok",
                        "reported_at_epoch": now}
                if name == "esp128":
                    meta["native_type"] = (
                        "BinarySensorState" if field in projection.BOOLEAN_FIELDS
                        else "SensorState")
                raw[name][field] = {"value": value, "meta": meta}
        return raw

    def test_complete_independent_off_snapshot_projects(self):
        proof = projection.project_off(self.snapshot())
        self.assertFalse(proof.autonomous)
        self.assertFalse(proof.lease_armed)
        self.assertEqual(0, proof.lease_remaining_s)
        self.assertEqual(900, proof.lease_ttl_s)

    def test_refuses_stale_snapshot(self):
        raw = self.snapshot()
        raw["captured_at_epoch"] -= 60
        with self.assertRaisesRegex(projection.TransactionError, "snapshot stale"):
            projection.project_off(raw)

    def test_refuses_bad_numeric_physical_value(self):
        raw = self.snapshot()
        raw["esp128"]["voltage_v"]["value"] = float("nan")
        with self.assertRaisesRegex(projection.TransactionError, "nonfinite"):
            projection.project_off(raw)

    def test_refuses_wrong_native_callback_type(self):
        raw = self.snapshot()
        raw["esp128"]["protection_r16"]["meta"]["native_type"] = "ButtonInfo"
        with self.assertRaisesRegex(projection.TransactionError, "callback type"):
            projection.project_off(raw)

    def test_refuses_nonphysical_safe_off_claim(self):
        raw = self.snapshot()
        raw["ha102"]["output_r18"]["value"] = 1
        with self.assertRaisesRegex(projection.TransactionError, "unsafe OFF"):
            projection.project_off(raw)

    def test_refuses_malformed_or_reused_source_nonces(self):
        for nonces in (["short", "b" * 32], ["a" * 32, "a" * 32]):
            with self.subTest(nonces=nonces):
                raw = self.snapshot()
                raw["source_nonces"] = nonces
                with self.assertRaisesRegex(projection.TransactionError, "nonces"):
                    projection.project_off(raw)

    def test_refuses_ha_native_disagreement(self):
        raw = self.snapshot()
        raw["esp128"]["set_voltage_v"]["value"] = 14.4
        with self.assertRaisesRegex(projection.TransactionError, "disagreement"):
            projection.project_off(raw)

    def test_refusal_does_not_mutate_input_or_issue_physical_calls(self):
        raw = self.snapshot()
        raw["esp128"]["lease_armed"]["value"] = True
        before = copy.deepcopy(raw)
        with self.assertRaises(projection.TransactionError):
            projection.project_off(raw)
        self.assertEqual(before, raw)
        self.assertFalse(hasattr(projection, "set_output"))
        self.assertFalse(hasattr(projection, "set_voltage"))


if __name__ == "__main__":
    unittest.main()
