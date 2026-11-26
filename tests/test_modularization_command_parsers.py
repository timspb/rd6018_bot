"""Golden behavior checks for the extracted pure command parsers."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.ui.commands.validation import _parse_three_values, _parse_two_numbers


ROOT = Path(__file__).resolve().parents[1]


class CommandParserBehaviorTests(unittest.TestCase):
    def test_two_numbers_success_comma_decimal_and_failures(self) -> None:
        self.assertEqual(_parse_two_numbers("16.50 1.4"), (16.5, 1.4))
        self.assertEqual(_parse_two_numbers(" 16,50   1,4 "), (16.5, 1.4))
        for text in ("", "16.5", "16.5 1.4 2", "16.5 nope", None):
            with self.subTest(text=text):
                self.assertIsNone(_parse_two_numbers(text))

    def test_timer_token_formats(self) -> None:
        self.assertEqual(
            _parse_three_values("16.5 2.0 2:35"),
            {"v": 16.5, "i": 2.0, "time_sec": 9300},
        )
        self.assertEqual(
            _parse_three_values("16,5 2,0 2:35:07"),
            {"v": 16.5, "i": 2.0, "time_sec": 9307},
        )

    def test_current_latin_and_cyrillic_units_and_exact_thresholds(self) -> None:
        limit = float(MAX_STAGE_CURRENT_A.default)
        self.assertEqual(_parse_three_values("16 2 0.1A"), {"v": 16.0, "i": 2.0, "off_current": 0.1})
        self.assertEqual(_parse_three_values(f"16 2 {limit}A"), {"v": 16.0, "i": 2.0, "off_current": limit})
        self.assertEqual(_parse_three_values("16 2 1,25А"), {"v": 16.0, "i": 2.0, "off_current": 1.25})
        self.assertIsNone(_parse_three_values("16 2 0.09A"))
        self.assertIsNone(_parse_three_values(f"16 2 {limit + 0.1}А"))

    def test_voltage_latin_and_cyrillic_units_and_exact_thresholds(self) -> None:
        self.assertEqual(_parse_three_values("16 2 0V"), {"v": 16.0, "i": 2.0, "off_voltage": 0.0})
        self.assertEqual(_parse_three_values("16 2 20В"), {"v": 16.0, "i": 2.0, "off_voltage": 20.0})
        self.assertEqual(_parse_three_values("16 2 15,4v"), {"v": 16.0, "i": 2.0, "off_voltage": 15.4})
        self.assertIsNone(_parse_three_values("16 2 -0.1В"))
        self.assertIsNone(_parse_three_values("16 2 20.1V"))

    def test_invalid_or_missing_duration_and_nonnumeric_inputs(self) -> None:
        for text in (
            "16 2", "16 2 0:00", "16 2 0:00:00", "16 2 2:3:4:5",
            "16 2 2:x", "x 2 1:00", "16 x 1:00", "16 2 nope",
            "16 2 2", "16 2 A", None,
        ):
            with self.subTest(text=text):
                self.assertIsNone(_parse_three_values(text))


class CommandParserExtractionTests(unittest.TestCase):
    def test_production_runtime_reexports_parsers_and_has_no_definitions(self) -> None:
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        old_definitions = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"_parse_two_numbers", "_parse_three_values"}
        }
        self.assertEqual(old_definitions, set())
        direct_imports = [
            node for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime.ui.commands.validation"
        ]
        imported = {alias.name for node in direct_imports for alias in node.names}
        self.assertTrue({"_parse_two_numbers", "_parse_three_values"} <= imported)

        # Static compatibility proof: do not import the effectful production monolith.
        self.assertEqual(
            {"_parse_two_numbers", "_parse_three_values"} & imported,
            {"_parse_two_numbers", "_parse_three_values"},
        )


if __name__ == "__main__":
    unittest.main()
