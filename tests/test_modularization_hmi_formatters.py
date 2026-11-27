"""Parity and ownership tests for the pure HMI formatters."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.ui.components.hmi_values import (
    format_electrical_data,
    format_status_data,
    format_temperature_data,
    safe_html_format,
)


ROOT = Path(__file__).resolve().parents[1]
FORMATTER_NAMES = {
    "format_electrical_data",
    "format_temperature_data",
    "format_status_data",
    "safe_html_format",
}


class HmiFormatterGoldenTests(unittest.TestCase):
    def test_electrical_data_formats_voltage_current_and_optional_power(self):
        self.assertEqual(format_electrical_data(12.345, 1.236, 15.26), "12.35В 1.24А 15.3Вт")
        self.assertEqual(format_electrical_data(12.0, 0.5), "12.00В 0.50А")

    def test_electrical_precision_argument_remains_ignored(self):
        self.assertEqual(format_electrical_data(12.345, 1.236, precision=0), "12.35В 1.24А")

    def test_temperature_threshold_and_warning(self):
        self.assertEqual(format_temperature_data(24.25), "🌡 АКБ 24.2°C")
        self.assertEqual(format_temperature_data(24.25, 50.0), "🌡 АКБ 24.2°C | БП 50.0°C")
        self.assertEqual(format_temperature_data(24.25, 50.1), "🌡 АКБ 24.2°C | БП 50.1°C ⚠️")

    def test_status_stage_is_html_escaped(self):
        self.assertEqual(
            format_status_data(True, "AUTO", "MAIN <bulk>"),
            "⚡️AUTO MAIN &lt;bulk&gt;",
        )
        self.assertEqual(format_status_data(False, "Manual"), "⏸️Manual")

    def test_safe_html_format_escapes_values_and_keeps_trusted_tags(self):
        self.assertEqual(
            safe_html_format("<b>{value}</b>", value="A&B <C>"),
            "<b>A&amp;B &lt;C&gt;</b>",
        )
        self.assertEqual(
            safe_html_format("{value}", value="<b>trusted</b>"),
            "<b>trusted</b>",
        )

    def test_safe_html_format_normalizes_none_and_hr_variants(self):
        self.assertEqual(
            safe_html_format("<hr>|<hr/>|<hr />|{missing}", missing=None),
            "___________________|___________________|___________________|",
        )


class HmiFormatterOwnershipTests(unittest.TestCase):
    def test_formatters_are_defined_in_component_and_reexported_by_runtime(self):
        hmi_path = ROOT / "runtime/ui/components/hmi_values.py"
        runtime_path = ROOT / "runtime/production_runtime.py"
        hmi_tree = ast.parse(hmi_path.read_text(encoding="utf-8"))
        runtime_tree = ast.parse(runtime_path.read_text(encoding="utf-8"))

        hmi_definitions = {
            node.name
            for node in hmi_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        runtime_definitions = {
            node.name
            for node in runtime_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        imported_names = {
            alias.name
            for node in runtime_tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime.ui.components.hmi_values"
            for alias in node.names
        }

        self.assertTrue(FORMATTER_NAMES <= hmi_definitions)
        self.assertTrue(FORMATTER_NAMES.isdisjoint(runtime_definitions))
        self.assertTrue(FORMATTER_NAMES <= imported_names)


if __name__ == "__main__":
    unittest.main()
