import pathlib
import unittest


class EspHomeFullTargetContractTests(unittest.TestCase):
    def setUp(self):
        self.text = pathlib.Path("esphome/rd6018_controller_v2.yaml").read_text(encoding="utf-8")

    def test_target_composes_all_v2_edge_packages(self):
        self.assertIn("safety_lease: !include rd6018_safety_lease.yaml", self.text)
        self.assertIn("telemetry_v2: !include rd6018_telemetry_v2.yaml", self.text)
        self.assertIn("live_adoption: !include rd6018_live_adoption.yaml", self.text)

    def test_target_uses_local_secrets_and_same_node_identity(self):
        self.assertIn('device_name: "rd6018-controller"', self.text)
        self.assertIn("key: !secret api_encryption_key", self.text)
        self.assertIn("ssid: !secret wifi_ssid", self.text)
        self.assertIn("password: !secret wifi_password", self.text)
        self.assertIn("password: !secret ota_password", self.text)

    def test_target_keeps_required_bot_entity_surface(self):
        for name in (
            'name: "Output voltage"',
            'name: "Output current"',
            'name: "Output Power"',
            'name: "Battery voltage"',
            'name: "Temperature"',
            'name: "Temperature external"',
            'name: "Over Voltage Protection"',
            'name: "Over Current Protection"',
            'name: "Constant Voltage"',
            'name: "Constant Current"',
            'name: "Output"',
        ):
            self.assertIn(name, self.text)

    def test_target_does_not_embed_obsolete_thirty_minute_lease(self):
        self.assertNotIn("1800000", self.text)

    def test_legacy_status_entities_are_derived_from_authoritative_raw_codes(self):
        self.assertIn("id(rd6018_protection_status_code).state", self.text)
        self.assertIn("id(rd6018_regulation_mode_code).state", self.text)
        self.assertNotIn("address: 16\n    register_type: holding\n    bitmask", self.text)
        self.assertNotIn("address: 17\n    register_type: holding\n    bitmask", self.text)


if __name__ == "__main__":
    unittest.main()
