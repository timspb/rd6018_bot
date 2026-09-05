from pathlib import Path
import unittest


class EspHomeSafetyLeaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path("esphome/packages/rd6018_safety_lease.yaml").read_text(
            encoding="utf-8"
        )

    def test_lease_is_fifteen_minutes_and_retries_local_off(self):
        self.assertIn('rd6018_safety_lease_ttl_ms: "900000"', self.text)
        self.assertIn("bot/HA -> renew every 5 min", self.text)
        self.assertIn("interval: 5s", self.text)
        self.assertIn("switch.turn_off: rd6018_safety_output", self.text)

    def test_direct_modbus_freshness_is_part_of_the_lease(self):
        self.assertIn('rd6018_safety_modbus_stale_ms: "20000"', self.text)
        self.assertIn("rd6018_safety_last_modbus_rx_ms", self.text)
        self.assertIn("address: 10", self.text)

    def test_output_off_proof_has_its_own_direct_register_readback_timestamp(self):
        self.assertIn("rd6018_safety_last_output_rx_ms", self.text)
        self.assertIn("rd6018_safety_output_on_readback", self.text)
        probe_block = self.text.split("id: rd6018_safety_output_probe", 1)[1].split(
            "- platform: template", 1
        )[0]
        self.assertIn("address: 18", probe_block)
        self.assertIn("id(rd6018_safety_last_output_rx_ms) = millis();", probe_block)
        self.assertIn("id(rd6018_safety_output_on_readback)", probe_block)

    def test_reboot_state_is_persisted_but_heartbeat_is_not(self):
        managed_block = self.text.split("- id: rd6018_safety_managed_session", 1)[1].split(
            "- id: rd6018_safety_lease_tripped", 1
        )[0]
        renew_block = self.text.split("- id: rd6018_safety_last_renew_ms", 1)[1].split(
            "- id: rd6018_safety_last_modbus_rx_ms", 1
        )[0]
        self.assertIn("restore_value: yes", managed_block)
        self.assertIn("restore_value: no", renew_block)

    def test_every_reboot_enters_fail_closed_quarantine(self):
        self.assertIn("id(rd6018_safety_boot_quarantine) = true;", self.text)
        self.assertIn("if (id(rd6018_safety_boot_quarantine)) return;", self.text)
        self.assertIn(
            "return id(rd6018_safety_boot_quarantine) ||",
            self.text,
        )
        self.assertIn(
            "telemetry_fresh && output_fresh && !id(rd6018_safety_output_on_readback)",
            self.text,
        )

    def test_trip_is_latched_until_fresh_register_18_confirms_off(self):
        self.assertIn("if (id(rd6018_safety_lease_tripped)) return;", self.text)
        self.assertIn(
            "if (!telemetry_fresh || !output_fresh || id(rd6018_safety_output_on_readback)) return;",
            self.text,
        )
        self.assertIn("id(rd6018_safety_lease_tripped) = false;", self.text)

    def test_initial_arm_requires_direct_output_off_but_heartbeat_may_run_while_on(self):
        self.assertIn(
            "if (!id(rd6018_safety_managed_session) && id(rd6018_safety_output_on_readback))",
            self.text,
        )

    def test_local_off_uses_standard_rd60xx_output_register(self):
        output_block = self.text.split("id: rd6018_safety_output\n", 1)[1].split("button:", 1)[0]
        self.assertIn("address: 18", output_block)
        self.assertIn("bitmask: 0x1", output_block)


if __name__ == "__main__":
    unittest.main()
