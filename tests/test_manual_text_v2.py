import unittest

from manual_text_v2 import parse_manual_command


class ManualTextV2Tests(unittest.TestCase):
    def test_plain_quick_command_accepts_full_manual_envelope(self):
        parsed = parse_manual_command("17.5 12")
        assert parsed is not None
        self.assertAlmostEqual(parsed.request.voltage_v, 17.5)
        self.assertAlmostEqual(parsed.request.current_a, 12.0)
        self.assertIsNone(parsed.reach_voltage_v)
        self.assertIsNone(parsed.reach_current_a)

    def test_above_absolute_manual_voltage_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_manual_command("17.5001 1")

    def test_legacy_third_current_is_exact_reach_not_one_sided_limit(self):
        parsed = parse_manual_command("16.5 1.5 1.00A")
        assert parsed is not None
        self.assertAlmostEqual(parsed.reach_current_a or 0.0, 1.0)
        self.assertIsNone(parsed.request.stop.current_ge_a)
        self.assertIsNone(parsed.request.stop.current_le_a)

    def test_legacy_third_voltage_is_exact_reach(self):
        parsed = parse_manual_command("16.5 1.5 16.20V")
        assert parsed is not None
        self.assertAlmostEqual(parsed.reach_voltage_v or 0.0, 16.2)
        self.assertIsNone(parsed.request.stop.voltage_ge_v)
        self.assertIsNone(parsed.request.stop.voltage_le_v)

    def test_explicit_conditions_can_be_combined(self):
        parsed = parse_manual_command(
            "16.5 1.5 2:00 V>=16.40 I<=0.30 delta=0.03"
        )
        assert parsed is not None
        stop = parsed.request.stop
        self.assertAlmostEqual(stop.max_active_seconds or 0.0, 7200.0)
        self.assertAlmostEqual(stop.voltage_ge_v or 0.0, 16.4)
        self.assertAlmostEqual(stop.current_le_a or 0.0, 0.3)
        self.assertAlmostEqual(stop.delta or 0.0, 0.03)

    def test_non_manual_text_falls_through(self):
        self.assertIsNone(parse_manual_command("покажи график за два часа"))

    def test_numeric_manual_prefix_with_unknown_condition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "неизвестное условие"):
            parse_manual_command("14.7 5 bananas")


if __name__ == "__main__":
    unittest.main()
