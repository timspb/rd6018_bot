"""Regression guards for internal UI handler naming cleanup."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("bot.py", "production_bot_ui.py", "manual_context.py")
RETIRED_INTERNAL_NAMES = (
    "_v2_select_quick_profile",
    "_v2_batteries_handler",
    "_v2_battery_add_handler",
    "_v2_manual_choose_handler",
    "_v2_manual_interrupted_handler",
    "_v2_bound_manual_middleware",
    "_v2_manual_context_ui_installed",
    "v2_status_handler",
)


class UiInternalHandlerNameTests(unittest.TestCase):
    def test_internal_handler_names_are_canonical_without_aliases(self) -> None:
        sources = {
            path.name: path.read_text(encoding="utf-8")
            for path in (ROOT / name for name in TARGETS)
        }
        for name, source in sources.items():
            for retired in RETIRED_INTERNAL_NAMES:
                self.assertNotIn(retired, source, f"{name}: {retired}")

        bot_source = sources["bot.py"]
        for canonical in (
            "app._select_quick_profile",
            "app._batteries_handler",
            "app._battery_add_handler",
            "app._manual_choose_handler",
            "app._manual_interrupted_handler",
        ):
            self.assertIn(canonical, bot_source)

    def test_external_callback_tokens_remain_unchanged(self) -> None:
        ui_source = (ROOT / "production_bot_ui.py").read_text(encoding="utf-8")
        manual_source = (ROOT / "manual_context.py").read_text(encoding="utf-8")
        for token in (
            'callback_data="v2_batteries"',
            'callback_data="v2_battery_add"',
            'callback_data="v2_manual_choose"',
            'F.data.startswith("v2_battery_")',
        ):
            self.assertIn(token, ui_source + manual_source)


if __name__ == "__main__":
    unittest.main()
