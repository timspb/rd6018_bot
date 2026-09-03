import unittest

from config import ENTITY_MAP


class DeployedV2EntityNamespaceTests(unittest.TestCase):
    def test_all_enabled_v2_telemetry_entities_use_device_prefixed_namespace(self):
        expected = {
            "power_v2": "sensor.rd6018_rd_6018_output_power_v2",
            "temp_int_v2": "sensor.rd6018_rd_6018_temperature_internal_v2",
            "temp_ext_v2": "sensor.rd6018_rd_6018_temperature_external_v2",
            "protection_code": "sensor.rd6018_rd_6018_protection_status_code",
            "regulation_code": "sensor.rd6018_rd_6018_regulation_mode_code",
            "output_state_code_v2": "sensor.rd6018_rd_6018_output_state_code_v2",
            "model_number": "sensor.rd6018_rd_6018_model_number_v2",
            "serial_number": "sensor.rd6018_rd_6018_serial_number_v2",
            "firmware_version": "sensor.rd6018_rd_6018_firmware_version_v2",
            "active_preset": "sensor.rd6018_rd_6018_active_preset_v2",
            "take_ok": "binary_sensor.rd6018_rd_6018_take_ok_v2",
            "take_out": "binary_sensor.rd6018_rd_6018_take_out_v2",
            "boot_power": "binary_sensor.rd6018_rd_6018_boot_power_v2",
        }
        for key, entity_id in expected.items():
            with self.subTest(key=key):
                self.assertEqual(ENTITY_MAP[key], entity_id)

    def test_disabled_calibration_entities_are_pinned_to_same_namespace(self):
        expected = {
            "cal_vout_zero": "sensor.rd6018_rd_6018_cal_vout_zero",
            "cal_vout_scale": "sensor.rd6018_rd_6018_cal_vout_scale",
            "cal_vbat_zero": "sensor.rd6018_rd_6018_cal_vbat_zero",
            "cal_vbat_scale": "sensor.rd6018_rd_6018_cal_vbat_scale",
            "cal_iout_zero": "sensor.rd6018_rd_6018_cal_iout_zero",
            "cal_iout_scale": "sensor.rd6018_rd_6018_cal_iout_scale",
            "cal_ibat_zero": "sensor.rd6018_rd_6018_cal_ibat_zero",
            "cal_ibat_scale": "sensor.rd6018_rd_6018_cal_ibat_scale",
        }
        for key, entity_id in expected.items():
            with self.subTest(key=key):
                self.assertEqual(ENTITY_MAP[key], entity_id)

    def test_no_v2_package_mapping_uses_legacy_unprefixed_namespace(self):
        package_keys = {
            "power_v2",
            "temp_int_v2",
            "temp_ext_v2",
            "protection_code",
            "regulation_code",
            "output_state_code_v2",
            "model_number",
            "serial_number",
            "firmware_version",
            "active_preset",
            "take_ok",
            "take_out",
            "boot_power",
            "cal_vout_zero",
            "cal_vout_scale",
            "cal_vbat_zero",
            "cal_vbat_scale",
            "cal_iout_zero",
            "cal_iout_scale",
            "cal_ibat_zero",
            "cal_ibat_scale",
        }
        for key in package_keys:
            with self.subTest(key=key):
                self.assertIn("rd6018_rd_6018_", ENTITY_MAP[key])
                self.assertNotIn(".rd_6018_", ENTITY_MAP[key])


if __name__ == "__main__":
    unittest.main()
