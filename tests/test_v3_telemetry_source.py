import unittest

from runtime.telemetry import TelemetryQualityStatus, normalize_live


class TelemetrySourceTests(unittest.TestCase):
    def test_normalizes_values_and_provenance(self):
        evidence = normalize_live(
            {
                "voltage": "14.42", "current": "2.1", "temp_ext": "30",
                "switch": "on", "set_voltage": "14.4", "set_current": "2.0",
                "ovp": "15", "ocp": "3", "_meta": {
                    key: {"last_reported": "2026-09-13T00:00:00+00:00"}
                    for key in ("voltage", "current", "temp_ext", "switch", "set_voltage", "set_current", "ovp", "ocp")
                },
                }, now=1799798401, max_age=10,
        )
        self.assertEqual(evidence.snapshot.voltage, 14.42)
        self.assertTrue(evidence.snapshot.output_state)
        self.assertTrue(evidence.snapshot.readback_valid)
        # The metadata timestamp is deliberately fresh for this deterministic case.
        fresh = normalize_live({"voltage": 14.42, "_meta": {"voltage": {"last_reported": 1799798400}}}, now=1799798401, max_age=10)
        self.assertEqual(fresh.quality("voltage").status, TelemetryQualityStatus.VALID)

    def test_missing_and_stale_are_field_local(self):
        evidence = normalize_live(
            {"voltage": 14.0, "_meta": {"voltage": {"last_reported": 1}}},
            now=20, max_age=10,
        )
        self.assertEqual(evidence.quality("voltage").status, TelemetryQualityStatus.STALE)
        self.assertEqual(evidence.quality("current").status, TelemetryQualityStatus.MISSING)

    def test_present_value_without_freshness_is_invalid(self):
        evidence = normalize_live({"voltage": 14.0}, now=20, max_age=10)
        self.assertEqual(evidence.quality("voltage").status, TelemetryQualityStatus.INVALID)


if __name__ == "__main__":
    unittest.main()
