import unittest
from datetime import datetime, timedelta, timezone

from rd6018_telemetry import (
    ProtectionStatus,
    RegulationMode,
    calibration_fingerprint,
    canonicalize_live,
    decode_protection_code,
    decode_regulation_code,
    power_consistency,
    relay_path_drop_v,
    resolve_protection,
    telemetry_freshness,
)


class RD6018TelemetryTests(unittest.TestCase):
    def test_protection_register_is_status_code_not_bitmask(self):
        self.assertEqual(decode_protection_code(0).status, ProtectionStatus.NORMAL)
        self.assertEqual(decode_protection_code(1).status, ProtectionStatus.OVP)
        self.assertEqual(decode_protection_code(2).status, ProtectionStatus.OCP)
        state = decode_protection_code(3)
        self.assertEqual(state.status, ProtectionStatus.OPP)
        self.assertTrue(state.opp)
        self.assertFalse(state.ovp)
        self.assertFalse(state.ocp)

    def test_legacy_both_protection_bits_is_unknown_trip(self):
        state = resolve_protection({"ovp_triggered": "on", "ocp_triggered": "on"})
        self.assertEqual(state.status, ProtectionStatus.UNKNOWN)
        self.assertTrue(state.tripped)

    def test_regulation_code_is_single_enum(self):
        self.assertEqual(decode_regulation_code(0), RegulationMode.CV)
        self.assertEqual(decode_regulation_code(1), RegulationMode.CC)
        self.assertEqual(decode_regulation_code(2), RegulationMode.UNKNOWN)

    def test_corrected_v2_channels_replace_legacy_canonical_values(self):
        live = {
            "power": 123456.0,
            "power_v2": 44.25,
            "temp_int": 65541.0,
            "temp_int_v2": -5.0,
            "temp_ext": 65539.0,
            "temp_ext_v2": -3.0,
            "protection_code": 3,
            "regulation_code": 0,
            "uptime": 1234,
        }
        canonicalize_live(live)
        self.assertEqual(live["power"], 44.25)
        self.assertEqual(live["temp_int"], -5.0)
        self.assertEqual(live["temp_ext"], -3.0)
        self.assertEqual(live["protection_status"], "opp")
        self.assertEqual(live["regulation_mode"], "cv")
        self.assertEqual(live["bridge_uptime"], 1234)

    def test_freshness_is_enforced_only_when_metadata_exists(self):
        self.assertTrue(telemetry_freshness({}, ["battery_voltage"]).valid)
        now = datetime.now(timezone.utc)
        good = {"_meta": {"battery_voltage": {"status": "ok", "last_updated": now.isoformat()}}}
        self.assertTrue(telemetry_freshness(good, ["battery_voltage"]).valid)
        old = (now - timedelta(seconds=30)).isoformat()
        stale = {"_meta": {"battery_voltage": {"status": "ok", "last_updated": old}}}
        self.assertFalse(telemetry_freshness(stale, ["battery_voltage"], max_age_s=20).valid)

    def test_relay_path_drop_is_observational_only_under_loaded_battery_mode(self):
        live = {"switch": "on", "battery_mode": "on", "current": 10.0, "voltage": 14.82, "battery_voltage": 14.79}
        self.assertAlmostEqual(relay_path_drop_v(live), 0.03, places=6)
        live["battery_mode"] = "off"
        self.assertIsNone(relay_path_drop_v(live))

    def test_power_consistency_compares_reported_power_to_v_times_i(self):
        report = power_consistency({"voltage": 14.0, "current": 3.0, "power": 42.1})
        assert report is not None
        self.assertTrue(report["consistent"])
        report = power_consistency({"voltage": 14.0, "current": 3.0, "power": 55.0})
        assert report is not None
        self.assertFalse(report["consistent"])

    def test_calibration_fingerprint_requires_all_coefficients(self):
        live = {"model_number": 60181, "serial_number": 123, "firmware_version": 1.41}
        for i, key in enumerate(("cal_vout_zero", "cal_vout_scale", "cal_vbat_zero", "cal_vbat_scale", "cal_iout_zero", "cal_iout_scale", "cal_ibat_zero", "cal_ibat_scale"), 1):
            live[key] = i
        fp = calibration_fingerprint(live)
        self.assertIsNotNone(fp)
        self.assertEqual(fp[-8:], tuple(range(1, 9)))


if __name__ == "__main__":
    unittest.main()
