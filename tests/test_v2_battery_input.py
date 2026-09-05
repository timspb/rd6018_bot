import unittest

from pb_domain import BatteryChemistry
from v2_battery_input import parse_battery_spec


class V2BatteryInputTests(unittest.TestCase):
    def test_whitespace_input_keeps_multiword_model(self):
        identity, _ = parse_battery_spec("varta70 AGM 70 Varta Silver Dynamic AGM")
        self.assertEqual(identity.battery_id, "varta70")
        self.assertEqual(identity.chemistry, BatteryChemistry.AGM)
        self.assertEqual(identity.nominal_capacity_ah, 70.0)
        self.assertEqual(identity.manufacturer, "Varta")
        self.assertEqual(identity.model, "Silver Dynamic AGM")

    def test_comma_input_is_supported(self):
        identity, _ = parse_battery_spec("topla70, EFB, 70, Topla, EFB Stop&Go")
        self.assertEqual(identity.chemistry, BatteryChemistry.EFB)
        self.assertEqual(identity.manufacturer, "Topla")
        self.assertEqual(identity.model, "EFB Stop&Go")

    def test_legacy_pipe_input_remains_compatible(self):
        identity, _ = parse_battery_spec("old70 | Ca/Ca | 70 | Mutlu | SFB")
        self.assertEqual(identity.chemistry, BatteryChemistry.CA_CA)
        self.assertEqual(identity.nominal_capacity_ah, 70.0)

    def test_capacity_may_include_ah_suffix(self):
        identity, _ = parse_battery_spec("agm95 AGM 95Ah Varta G14")
        self.assertEqual(identity.nominal_capacity_ah, 95.0)


if __name__ == "__main__":
    unittest.main()
