import unittest

from presentation.dark_panel import render_dark_dashboard, render_dark_panel


class DarkPanelTests(unittest.TestCase):
    def test_renderer_returns_png_from_rendered_text(self):
        image = render_dark_panel("<b>RD6018 · Baic72 · CV</b>\nРУЧНОЙ · MAIN\nImin=0.10 A")
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(image), 100)

    def test_renderer_omits_empty_lines_and_markup(self):
        image = render_dark_panel("<b>RD6018</b>\n\n  \nCV")
        self.assertTrue(image.startswith(b"\x89PNG"))

    def test_dashboard_composes_chart_and_panel(self):
        chart = render_dark_panel("chart")
        dashboard = render_dark_dashboard(chart, "panel")
        self.assertTrue(dashboard.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(dashboard), len(chart))


if __name__ == "__main__":
    unittest.main()
