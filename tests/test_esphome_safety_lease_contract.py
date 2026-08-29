from pathlib import Path
import unittest


class EspHomeSafetyLeaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path("esphome/rd6018_safety_lease.yaml").read_text(encoding="utf-8")

    def test_lease_is_thirty_minutes_and_retries_local_off(self):
        self.assertIn('rd6018_safety_lease_ttl_ms: "1800000"', self.text)
        self.assertIn("interval: 5s", self.text)
        self.assertIn("switch.turn_off: rd6018_safety_output", self.text)

    def test_direct_modbus_freshness_is_part_of_the_lease(self):
        self.assertIn('rd6018_safety_modbus_stale_ms: "20000"', self.text)
        self.assertIn("rd6018_safety_last_modbus_rx_ms", self.text)
        self.assertIn("address: 10", self.text)

    def test_reboot_state_is_persisted_but_heartbeat_is_not(self):
        managed_block = self.text.split("- id: rd6018_safety_managed_session", 1)[1].split(
            "- id: rd6018_safety_lease_tripped", 1
        )[0]
        renew_block = self.text.split("- id: rd6018_safety_last_renew_ms", 1)[1].split(
            "- id: rd6018_safety_last_modbus_rx_ms", 1
        )[0]
        self.assertIn("restore_value: yes", managed_block)
        self.assertIn("restore_value: no", renew_block)

    def test_trip_is_latched_until_verified_off_disarm(self):
        self.assertIn("if (id(rd6018_safety_lease_tripped)) return;", self.text)
        self.assertIn("if (!modbus_fresh || id(rd6018_safety_output).state) return;", self.text)


if __name__ == "__main__":
    unittest.main()
