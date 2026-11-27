"""B1052: unchanged HA autonomous is advisory; fresh ESP Native is authoritative."""
from datetime import datetime, timezone
import copy
import time
import unittest

from tools import node104_d106_live_observer as live
from tools import node104_d106_readonly_projection as projection
from tests.test_node104_d106_projection_portability import D106ProjectionPortabilityTests


class HAStaleAutonomousTests(unittest.TestCase):
    def snapshot(self):
        return D106ProjectionPortabilityTests().snapshot()

    def make_advisory(self):
        snap = self.snapshot()
        snap["ha102"]["autonomous"]["meta"]["reported_at_epoch"] -= 14460
        snap["ha102"]["autonomous"]["meta"]["status"] = "stale_advisory"
        return snap

    def test_stale_ha_autonomous_false_advisory_with_fresh_native_projects(self):
        raw = self.make_advisory()
        before = copy.deepcopy(raw)
        proof = projection.project_off(raw)
        self.assertFalse(proof.autonomous)
        self.assertEqual(900, proof.lease_ttl_s)
        self.assertEqual(before, raw)

    def test_unmarked_stale_ha_autonomous_still_refused(self):
        raw = self.make_advisory()
        raw["ha102"]["autonomous"]["meta"]["status"] = "ok"
        with self.assertRaisesRegex(projection.TransactionError, "stale source"):
            projection.project_off(raw)

    def test_advisory_on_fresh_ha_is_refused(self):
        raw = self.make_advisory()
        raw["ha102"]["autonomous"]["meta"]["reported_at_epoch"] = time.time()
        with self.assertRaisesRegex(projection.TransactionError, "quality"):
            projection.project_off(raw)

    def test_advisory_cannot_apply_to_any_other_ha_field(self):
        raw = self.make_advisory()
        raw["ha102"]["output_r18"]["meta"]["status"] = "stale_advisory"
        raw["ha102"]["output_r18"]["meta"]["reported_at_epoch"] -= 14460
        with self.assertRaisesRegex(projection.TransactionError, "stale source"):
            projection.project_off(raw)

    def test_stale_native_autonomous_always_refused(self):
        raw = self.make_advisory()
        raw["esp128"]["autonomous"]["meta"]["reported_at_epoch"] -= 14460
        with self.assertRaisesRegex(projection.TransactionError, "stale source"):
            projection.project_off(raw)

    def test_stale_ha_true_is_not_allowed_to_corrobate_off(self):
        raw = self.make_advisory()
        raw["ha102"]["autonomous"]["value"] = True
        with self.assertRaisesRegex(projection.TransactionError, "unsafe OFF"):
            projection.project_off(raw)

    def test_native_true_is_not_allowed_regardless_of_stale_ha_false(self):
        raw = self.make_advisory()
        raw["esp128"]["autonomous"]["value"] = True
        with self.assertRaisesRegex(projection.TransactionError, "unsafe OFF"):
            projection.project_off(raw)

    def test_missing_unknown_or_fake_ha_value_fails_closed(self):
        for bad in (None, "unknown", 0):
            with self.subTest(bad=bad):
                raw = self.make_advisory()
                raw["ha102"]["autonomous"]["value"] = bad
                with self.assertRaises(projection.TransactionError):
                    projection.project_off(raw)

    def test_malformed_or_future_stale_ha_timestamp_fails(self):
        now = time.time()
        for last in (None, "NOT_DATE", datetime.fromtimestamp(now + 600, timezone.utc).isoformat()):
            with self.subTest(last=last):
                data = {"state": "off", "last_reported": last}
                with self.assertRaises(Exception):
                    live._ha_record("autonomous", "binary_sensor.esp_autonomous", data, now)

    def test_producer_stale_binary_record_projects_without_faking_freshness(self):
        snap = self.snapshot()
        now = snap["captured_at_epoch"]
        when = datetime.fromtimestamp(now - 14460, timezone.utc).isoformat()
        snap["ha102"]["autonomous"] = live._ha_record(
            "autonomous", "binary_sensor.esp_autonomous",
            {"state": "off", "last_reported": when}, now)
        self.assertEqual("stale_advisory", snap["ha102"]["autonomous"]["meta"]["status"])
        self.assertAlmostEqual(now - 14460,
                               snap["ha102"]["autonomous"]["meta"]["reported_at_epoch"],
                               delta=.001)
        self.assertFalse(projection.project_off(snap, now=now).autonomous)

    def test_live_record_preserves_real_stale_timestamp_and_source(self):
        now = time.time()
        when = datetime.fromtimestamp(now - 14460, timezone.utc).isoformat()
        record = live._ha_record("autonomous", "binary_sensor.esp_autonomous",
                                  {"state": "off", "last_reported": when}, now)
        self.assertEqual("stale_advisory", record["meta"]["status"])
        self.assertEqual("ha102_rest", record["meta"]["source"])
        self.assertAlmostEqual(now - 14460, record["meta"]["reported_at_epoch"], delta=.001)
        self.assertFalse(record["value"])

    def test_live_other_ha_fields_remain_strict(self):
        now = time.time()
        when = datetime.fromtimestamp(now - 14460, timezone.utc).isoformat()
        with self.assertRaises(Exception):
            live._ha_record("output_r18", "sensor.esp_output",
                             {"state": "0", "last_reported": when}, now)

    def test_live_fresh_ha_autonomous_remains_normal_evidence(self):
        now = time.time()
        when = datetime.fromtimestamp(now - 0.5, timezone.utc).isoformat()
        record = live._ha_record("autonomous", "binary_sensor.esp_autonomous",
                                  {"state": "off", "last_reported": when}, now)
        self.assertEqual("ok", record["meta"]["status"])


if __name__ == "__main__":
    unittest.main()
