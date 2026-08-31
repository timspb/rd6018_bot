import pathlib
import unittest


class EspHomeLiveAdoptionContractTests(unittest.TestCase):
    def test_live_adoption_preserves_output_and_requires_exact_lease_contract(self):
        text = pathlib.Path("esphome/rd6018_live_adoption.yaml").read_text(encoding="utf-8")

        self.assertIn('name: "Safety Lease Adopt Live Output"', text)
        self.assertIn("if (${rd6018_safety_lease_ttl_ms}UL != 900000UL) return;", text)
        self.assertIn("if (id(rd6018_safety_boot_quarantine)) return;", text)
        self.assertIn("if (id(rd6018_safety_lease_tripped)) return;", text)
        self.assertIn("if (!control_fresh) return;", text)
        self.assertIn("if (id(rd6018_safety_managed_session)) return;", text)
        self.assertIn("if (!id(rd6018_safety_output_on_readback)) return;", text)
        self.assertIn("id(rd6018_safety_managed_session) = true;", text)
        self.assertIn("id(rd6018_safety_last_renew_ms) = now;", text)
        self.assertIn("id(rd6018_safety_generation)++;", text)

        # Ownership acquisition must never become a hidden setpoint/Output write.
        self.assertNotIn("switch.turn_on", text)
        self.assertNotIn("switch.turn_off", text)
        self.assertNotIn("create_write_single_command", text)


if __name__ == "__main__":
    unittest.main()
