from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class V3HomeCommandCutoverTests(unittest.TestCase):
    def test_historical_start_route_is_removed(self):
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('Command("start")', source)
        self.assertNotIn("async def cmd_start(", source)

    def test_canonical_home_adapter_has_no_historical_or_physical_imports(self):
        source = (ROOT / "runtime" / "ui" / "telegram" / "home.py").read_text(encoding="utf-8")
        for forbidden in (
            "runtime.v2_runtime",
            "charge_logic",
            "charge_controller",
            "hass_api",
            "runtime_safety",
            "safe_output",
            "esphome",
        ):
            self.assertNotIn(forbidden, source)

    def test_production_composition_installs_home_command(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("from runtime.ui.telegram.home import install_home_command", source)
        self.assertIn("install_home_command(", source)
        self.assertIn("render_home=app._build_and_send_dashboard", source)


if __name__ == "__main__":
    unittest.main()
