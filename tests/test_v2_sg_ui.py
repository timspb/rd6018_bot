import unittest

from v2_sg_ui import parse_sg_input


class V2SpecificGravityUiTests(unittest.TestCase):
    def test_six_cells_temperature_and_context_are_parsed(self):
        parsed = parse_sg_input(
            "1.275 1.272 1.270 1.180 1.274 1.271; t=25; context=post_charge; note=retest"
        )
        self.assertEqual(len(parsed.cells), 6)
        self.assertAlmostEqual(parsed.cells[3] or 0.0, 1.180)
        self.assertAlmostEqual(parsed.temperature_c or 0.0, 25.0)
        self.assertEqual(parsed.context, "post_charge")
        self.assertEqual(parsed.notes, "retest")

    def test_inaccessible_cell_is_explicit_none(self):
        parsed = parse_sg_input("1.270 1.269 - 1.268 1.271 1.270")
        self.assertIsNone(parsed.cells[2])

    def test_decimal_comma_is_accepted(self):
        parsed = parse_sg_input("1,270 1,269 1,268 1,267 1,266 1,265; t=24,5")
        self.assertAlmostEqual(parsed.cells[0] or 0.0, 1.270)
        self.assertAlmostEqual(parsed.temperature_c or 0.0, 24.5)

    def test_wrong_cell_count_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_sg_input("1.27 1.27 1.27")


if __name__ == "__main__":
    unittest.main()
