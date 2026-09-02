from pathlib import Path
import unittest


class EspHomeHandsOffReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path("esphome/packages/rd6018_safety_lease.yaml").read_text(
            encoding="utf-8"
        )

    def _release_section(self):
        start = self.text.index("id: rd6018_safety_lease_release_to_hands_off_button")
        end = self.text.index("\ninterval:", start)
        return self.text[start:end]

    def test_live_release_is_separate_from_verified_off_disarm(self):
        section = self._release_section()
        self.assertIn('name: "Safety Lease Release To Hands Off"', section)
        self.assertIn("if (!id(rd6018_safety_managed_session)) return;", section)
        self.assertIn("id(rd6018_safety_managed_session) = false;", section)
        self.assertIn("id(rd6018_safety_generation)++;", section)
        self.assertNotIn("rd6018_safety_output_on_readback", section)
        self.assertNotIn("switch.turn_off", section)

    def test_live_release_cannot_clear_trip_or_boot_quarantine(self):
        section = self._release_section()
        self.assertIn("if (id(rd6018_safety_boot_quarantine)) return;", section)
        self.assertIn("if (id(rd6018_safety_lease_tripped)) return;", section)
        self.assertNotIn("rd6018_safety_lease_tripped) = false", section)
        self.assertNotIn("rd6018_safety_boot_quarantine) = false", section)

    def test_normal_disarm_still_requires_direct_output_off(self):
        start = self.text.index("id: rd6018_safety_lease_disarm_button")
        end = self.text.index("id: rd6018_safety_lease_release_to_hands_off_button", start)
        section = self.text[start:end]
        self.assertIn("id(rd6018_safety_output_on_readback)) return;", section)


if __name__ == "__main__":
    unittest.main()
