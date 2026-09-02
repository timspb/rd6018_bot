import pathlib
import unittest


class EspHomeFullTargetContractTests(unittest.TestCase):
    def setUp(self):
        self.text = pathlib.Path("esphome/rd6018.yaml").read_text(encoding="utf-8")

    def test_canonical_target_composes_packages_from_subdirectory(self):
        self.assertIn(
            "safety_lease: !include packages/rd6018_safety_lease.yaml", self.text
        )
        self.assertIn(
            "telemetry_v2: !include packages/rd6018_telemetry_v2.yaml", self.text
        )
        self.assertIn(
            "live_adoption: !include packages/rd6018_live_adoption.yaml", self.text
        )
        for path in (
            "esphome/packages/rd6018_safety_lease.yaml",
            "esphome/packages/rd6018_telemetry_v2.yaml",
            "esphome/packages/rd6018_live_adoption.yaml",
        ):
            self.assertTrue(pathlib.Path(path).is_file(), path)

    def test_target_uses_prefixed_local_secrets_and_same_node_identity(self):
        self.assertIn('device_name: "rd6018-controller"', self.text)
        for secret in (
            "rd6018_api_encryption_key",
            "rd6018_ota_password",
            "rd6018_wifi_ssid",
            "rd6018_wifi_password",
            "rd6018_static_ip",
            "rd6018_gateway",
            "rd6018_subnet",
            "rd6018_fallback_ap_password",
        ):
            self.assertIn(f"!secret {secret}", self.text)

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
        self.assertNotIn(
            "address: 16\n    register_type: holding\n    bitmask", self.text
        )
        self.assertNotIn(
            "address: 17\n    register_type: holding\n    bitmask", self.text
        )

    def test_example_secrets_are_prefixed_and_production_secrets_are_ignored(self):
        example = pathlib.Path("esphome/secrets.example.yaml").read_text(
            encoding="utf-8"
        )
        keys = [
            line.split(":", 1)[0]
            for line in example.splitlines()
            if line and not line.startswith("#")
        ]
        self.assertTrue(keys)
        self.assertTrue(all(key.startswith("rd6018_") for key in keys))

        ignore = pathlib.Path(".gitignore").read_text(encoding="utf-8")
        self.assertIn("esphome/secrets.yaml", ignore)

    def test_ci_and_local_build_share_canonical_build_script(self):
        build = pathlib.Path("esphome/build_firmware.sh").read_text(encoding="utf-8")
        workflow = pathlib.Path(".github/workflows/esphome.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ESPHOME_VERSION=\"${ESPHOME_VERSION:-2026.8.2}\"", build)
        self.assertIn('TARGET="$ESPHOME_DIR/rd6018.yaml"', build)
        self.assertIn("./esphome/build_firmware.sh", workflow)
        self.assertIn("ESPHOME_SECRETS_MODE: example", workflow)


if __name__ == "__main__":
    unittest.main()
