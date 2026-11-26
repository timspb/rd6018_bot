"""Pure parity tests for the legacy OFF-condition text parser migration."""

import ast
import pathlib
import unittest
from unittest.mock import patch

from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.ui.commands.validation import _parse_off_command


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = ROOT / "runtime" / "production_runtime.py"


class OffTextParserTests(unittest.TestCase):
    def parse(self, text, now=1234.5):
        with patch("runtime.ui.commands.validation.time.time", return_value=now):
            return _parse_off_command(text)

    def test_exact_off_and_non_off_inputs_return_none(self):
        for value in (None, "", "off", " OFF ", "stop 15", "off\t15"):
            with self.subTest(value=value):
                self.assertIsNone(self.parse(value))

    def test_decimal_comma_and_case_and_outer_space_are_preserved(self):
        result = self.parse("  OfF   V>=15,5  ")
        self.assertEqual(result["voltage_ge"], 15.5)
        self.assertEqual(result["parts"], ["V≥15.5 В"])

    def test_ascii_and_unicode_comparison_operators_and_thresholds(self):
        result = self.parse("off V>=0 V<=20 I>=0.1 I<=30")
        self.assertEqual(
            (result["voltage_ge"], result["voltage_le"], result["current_ge"], result["current_le"]),
            (0.0, 20.0, 0.1, 30.0),
        )
        self.assertNotIn("I≤30.00 А", result["parts"])
        unicode = self.parse("off V≥15,2 V≤13,2 I≥1,25 I≤2,5")
        self.assertEqual(
            (unicode["voltage_ge"], unicode["voltage_le"], unicode["current_ge"], unicode["current_le"]),
            (15.2, 13.2, 1.25, 2.5),
        )

    def test_numeric_shorthand_ranges_and_existing_precedence(self):
        voltage = self.parse("off 12")
        self.assertEqual(voltage["voltage_ge"], 12.0)
        self.assertIsNone(voltage["current_le"])
        current = self.parse("off 0.1")
        self.assertEqual(current["current_le"], 0.1)
        # The upper end of the overlapping shorthand ranges remains voltage.
        self.assertEqual(self.parse("off 18")["voltage_ge"], 18.0)
        self.assertEqual(self.parse("off 11.99")["current_le"], 11.99)

    def test_current_threshold_uses_canonical_limit_and_rejects_above_it(self):
        maximum = float(MAX_STAGE_CURRENT_A.default)
        self.assertEqual(self.parse(f"off I>={maximum}")["current_ge"], maximum)
        over_limit = self.parse(f"off I<={maximum + 0.01}")
        # Legacy parser stores out-of-range comparisons but omits their label.
        self.assertEqual(over_limit["current_le"], maximum + 0.01)
        self.assertEqual(over_limit["parts"], [])

    def test_multiple_timers_are_additive(self):
        result = self.parse("off 0:30 1:00:15 0:00:45")
        self.assertEqual(result["time_sec"], 5460.0)
        self.assertEqual(result["parts"], ["таймер 0:30", "таймер 1:00:15", "таймер 0:00:45"])

    def test_timer_formats_and_timestamp(self):
        two_part = self.parse("off 2:35", now=77.25)
        self.assertEqual(two_part["time_sec"], 9300.0)
        self.assertEqual(two_part["start_time"], 77.25)
        three_part = self.parse("off 1:02:03")
        self.assertEqual(three_part["time_sec"], 3723.0)

    def test_invalid_only_inputs_return_none_and_invalid_tokens_are_skipped(self):
        for value in ("off nope", "off 0:00", "off 1:2:3:4"):
            with self.subTest(value=value):
                self.assertIsNone(self.parse(value))
        invalid_comparisons = self.parse("off V>=21 V<=-1 I>=0 I<=999")
        self.assertEqual(
            (invalid_comparisons["voltage_ge"], invalid_comparisons["voltage_le"],
             invalid_comparisons["current_ge"], invalid_comparisons["current_le"]),
            (21.0, -1.0, 0.0, 999.0),
        )
        self.assertEqual(invalid_comparisons["parts"], [])
        mixed = self.parse("off V>=21 2:35 malformed")
        self.assertEqual(mixed["voltage_ge"], 21.0)
        self.assertEqual(mixed["time_sec"], 9300.0)
        self.assertEqual(mixed["parts"], ["таймер 2:35"])

    def test_production_runtime_directly_reexports_parser_without_wrapper(self):
        tree = ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))
        imports = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime.ui.commands.validation"
        ]
        self.assertTrue(any(
            any(alias.name == "_parse_off_command" and alias.asname is None for alias in node.names)
            for node in imports
        ))
        self.assertFalse(any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_parse_off_command"
            for node in tree.body
        ))


if __name__ == "__main__":
    unittest.main()
