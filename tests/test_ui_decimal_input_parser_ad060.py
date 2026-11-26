import unittest

from runtime.ui.commands.validation import parse_decimal_number


class DecimalInputParserAD060Tests(unittest.TestCase):
    def test_accepts_dot_and_comma_decimal(self):
        self.assertEqual(parse_decimal_number("1.25"), 1.25)
        self.assertEqual(parse_decimal_number(" 1,25 "), 1.25)

    def test_rejects_empty_and_non_numeric_text(self):
        for value in ("", "   ", "abc", "1,2,3"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_decimal_number(value)


if __name__ == "__main__":
    unittest.main()
