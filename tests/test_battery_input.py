import unittest

from pb_domain import BatteryChemistry
from battery_input import parse_battery_spec


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

    def test_telegram_legacy_parser_has_one_owner(self):
        import pathlib
        import production_bot_ui
        from battery_input import parse_legacy_pipe_battery_spec
        source = pathlib.Path(production_bot_ui.__file__).read_text(encoding="utf-8")
        self.assertIn("parse_legacy_pipe_battery_spec as parse_battery_spec", source)
        self.assertNotIn("def parse_battery_spec(", source)
        sample = "old72 | Ca/Ca | 72 | Leoch | Ca/Ca"
        self.assertEqual(production_bot_ui.parse_battery_spec(sample),
                         parse_legacy_pipe_battery_spec(sample))

    def test_telegram_legacy_pipe_parser_preserves_strict_grammar(self):
        from battery_input import parse_legacy_pipe_battery_spec
        identity, lifecycle = parse_legacy_pipe_battery_spec("old72 | Ca/Ca | 72,0 | Leoch | Ca/Ca")
        self.assertEqual(identity.battery_id, "old72")
        self.assertEqual(identity.nominal_capacity_ah, 72.0)
        self.assertEqual(identity.chemistry, BatteryChemistry.CA_CA)
        self.assertEqual(identity.manufacturer, "Leoch")
        self.assertEqual(identity.model, "Ca/Ca")
        with self.assertRaisesRegex(ValueError, "формат"):
            parse_legacy_pipe_battery_spec("old72 AGM 72 Leoch")

    def test_telegram_legacy_pipe_parser_rejects_invalid_capacity(self):
        from battery_input import parse_legacy_pipe_battery_spec
        for value in ("0", "-1", "1001", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_legacy_pipe_battery_spec(f"bad | EFB | {value} | Vendor | Model")

    def test_capacity_may_include_ah_suffix(self):
        identity, _ = parse_battery_spec("agm95 AGM 95Ah Varta G14")
        self.assertEqual(identity.nominal_capacity_ah, 95.0)


if __name__ == "__main__":
    unittest.main()
