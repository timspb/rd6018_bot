import pathlib
import unittest


class ESPHomeTelemetryV2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path("esphome/rd6018_telemetry_v2.yaml").read_text(encoding="utf-8")

    def test_output_power_uses_register_13_not_12_u_dword(self):
        self.assertIn('name: "Output Power V2"', self.text)
        block = self.text.split('name: "Output Power V2"', 1)[1].split("- platform:", 1)[0]
        self.assertIn("address: 13", block)
        self.assertIn("value_type: U_WORD", block)
        self.assertNotIn("address: 12", block)
        self.assertNotIn("U_DWORD", block)

    def test_temperature_uses_explicit_sign_and_magnitude_registers(self):
        self.assertIn("address: 4", self.text)
        self.assertIn("address: 5", self.text)
        self.assertIn("address: 34", self.text)
        self.assertIn("address: 35", self.text)
        self.assertNotIn("value_type: S_DWORD", self.text)

    def test_raw_status_codes_are_exposed_without_fake_bitmask_protection(self):
        protection = self.text.split('name: "Protection Status Code"', 1)[1].split("- platform:", 1)[0]
        regulation = self.text.split('name: "Regulation Mode Code"', 1)[1].split("- platform:", 1)[0]
        self.assertIn("address: 16", protection)
        self.assertNotIn("bitmask", protection)
        self.assertIn("address: 17", regulation)
        self.assertNotIn("bitmask", regulation)

    def test_boot_and_preset_safety_configuration_is_observable(self):
        self.assertIn("address: 66", self.text)
        self.assertIn("address: 67", self.text)
        self.assertIn("address: 68", self.text)
        self.assertIn('name: "Active Preset V2"', self.text)

    def test_calibration_is_read_only_sensor_surface(self):
        for address in range(55, 63):
            self.assertIn(f"address: {address}", self.text)
        self.assertNotIn("number:\n", self.text)


if __name__ == "__main__":
    unittest.main()
