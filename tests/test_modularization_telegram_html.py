"""Source-only compatibility checks for the Telegram HTML formatter extraction."""

import ast
import unittest
from pathlib import Path

from runtime.ui.components.hmi_values import _md_to_html, _sanitize_telegram_html


ROOT = Path(__file__).resolve().parents[1]


class TelegramHtmlFormatterTests(unittest.TestCase):
    def test_markdown_golden_vectors(self):
        cases = (
            ("", ""),
            ("plain text", "plain text"),
            ("**bold**", "<b>bold</b>"),
            ("before **bold** after", "before <b>bold</b> after"),
            ("**one** and **two**", "<b>one</b> and <b>two</b>"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(_md_to_html(source), expected)

    def test_sanitizer_golden_vectors(self):
        cases = (
            ("", ""),
            ("plain text", "plain text"),
            ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
            (
                "<b>B</b><i>I</i><code>C</code><pre>P</pre>",
                "<b>B</b><i>I</i><code>C</code><pre>P</pre>",
            ),
            ("<br>", "<br>"),
            ("<br/>", "<br/>"),
            ("<br />", "<br />"),
            ("A & B", "A &amp; B"),
            (
                "**bold** & <b>safe</b> <img src=x> <br />",
                "**bold** &amp; <b>safe</b> &lt;img src=x&gt; <br />",
            ),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(_sanitize_telegram_html(source), expected)

    def test_source_definitions_and_compatibility_aliases_via_ast(self):
        component = ast.parse((ROOT / "runtime/ui/components/hmi_values.py").read_text(encoding="utf-8"))
        production = ast.parse((ROOT / "runtime/production_runtime.py").read_text(encoding="utf-8"))
        component_defs = {
            node.name: node
            for node in component.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        production_defs = {
            node.name
            for node in production.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        for name in ("_md_to_html", "_sanitize_telegram_html"):
            with self.subTest(name=name):
                self.assertIn(name, component_defs)
                self.assertEqual(
                    [arg.arg for arg in component_defs[name].args.args], ["text"]
                )
                self.assertNotIn(name, production_defs)

        imported_aliases = {
            alias.name: alias.asname
            for node in production.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "runtime.ui.components.hmi_values"
            for alias in node.names
        }
        self.assertEqual(imported_aliases["_md_to_html"], None)
        self.assertEqual(imported_aliases["_sanitize_telegram_html"], None)


if __name__ == "__main__":
    unittest.main()
