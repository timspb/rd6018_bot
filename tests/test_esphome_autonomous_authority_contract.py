from pathlib import Path
import unittest


class EspHomeAutonomousAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(
            "esphome/packages/rd6018_autonomous_authority.yaml"
        ).read_text(encoding="utf-8")
        cls.target = Path("esphome/rd6018.yaml").read_text(encoding="utf-8")

    def test_target_includes_autonomous_authority_package(self):
        self.assertIn(
            "autonomous_authority: !include packages/rd6018_autonomous_authority.yaml",
            self.target,
        )

    def test_persistent_read_only_runtime_entity_exists(self):
        self.assertIn("id: rd6018_safety_autonomous_mode", self.package)
        self.assertIn("restore_value: yes", self.package)
        self.assertIn("id: rd6018_safety_autonomous_mode_sensor", self.package)
        self.assertIn('name: "Safety Autonomous Mode"', self.package)

    def test_entry_and_exit_are_explicit_off_only_transitions(self):
        self.assertIn("id: rd6018_safety_enter_autonomous_button", self.package)
        self.assertIn("id: rd6018_safety_exit_autonomous_button", self.package)
        self.assertGreaterEqual(
            self.package.count("if (id(rd6018_safety_output_on_readback)) return;"),
            2,
        )
        self.assertNotIn("switch.turn_on", self.package)

    def test_transitions_require_fresh_direct_edge_evidence(self):
        self.assertGreaterEqual(
            self.package.count("telemetry_fresh &&"), 0
        )
        self.assertGreaterEqual(self.package.count("!telemetry_fresh"), 2)
        self.assertGreaterEqual(self.package.count("!output_fresh"), 2)

    def test_contract_does_not_contain_secrets_or_addresses(self):
        lowered = self.package.lower()
        for forbidden in ("!secret", "ssid", "password", "manual_ip", "api:"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
