from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from runtime.ui.actions import UIAction
from runtime.ui.screen import ScreenId
from runtime.ui.screens.help import build_help_screen
from runtime.ui.telegram.help import install_help_screen
from runtime.ui.telegram.renderer import render_screen_text


ROOT = Path(__file__).resolve().parents[1]


class _RouterGroup:
    def __init__(self) -> None:
        self.handlers = []

    def __call__(self, _filter):
        def decorate(func):
            self.handlers.append(func)
            return func
        return decorate


class _Router:
    def __init__(self) -> None:
        self.message = _RouterGroup()


class _Message:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=42)
        self.from_user = SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class _App:
    def __init__(self) -> None:
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")

    async def _check_chat_and_respond(self, _message):
        return True


class V3HelpUICutoverTests(unittest.TestCase):
    def test_help_screen_preserves_operator_copy(self):
        screen = build_help_screen()
        text = render_screen_text(screen)
        self.assertEqual(screen.screen_id, ScreenId.HELP)
        self.assertIn("<b>RD6018: быстрые команды</b>", text)
        self.assertIn("• /modes — режимы заряда", text)
        self.assertIn("• <b>AGM</b>", text)
        self.assertIn("⚠️ Перед высоким напряжением (до 16.5В)", text)

    def test_help_action_is_registered_navigation_only(self):
        from runtime.ui.routing.registry import route_for

        route = route_for(UIAction.OPEN_HELP)
        self.assertTrue(route.navigation_only)
        self.assertIsNone(route.intent_kind)

    def test_historical_help_command_is_removed(self):
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('Command("help")', source)
        self.assertNotIn("async def cmd_help(", source)
        self.assertNotIn("RD6018: быстрые команды", source)

    def test_composition_installs_help_screen(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        provider = source.index("operator_interface = OperatorSnapshotProvider(")
        install = source.index("install_help_screen(")
        self.assertLess(provider, install)

    def test_canonical_help_tree_has_no_historical_or_physical_imports(self):
        for rel in (
            "runtime/ui/components/help.py",
            "runtime/ui/screens/help.py",
            "runtime/ui/telegram/help.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            for forbidden in (
                "runtime.v2_runtime",
                "charge_controller",
                "charge_logic",
                "hass_api",
                "runtime_safety",
                "safe_output",
                "esphome",
            ):
                self.assertNotIn(forbidden, source, f"{rel}: {forbidden}")


class V3HelpTelegramRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_command_uses_canonical_screen_and_preserves_refresh(self):
        app = _App()
        refresh = []

        def schedule(chat_id: int, user_id: int) -> None:
            refresh.append((chat_id, user_id))

        install_help_screen(app, schedule_refresh=schedule)
        message = _Message()
        await app._v3_help_handler(message)

        self.assertEqual(len(message.answers), 1)
        text, kwargs = message.answers[0]
        self.assertEqual(text, render_screen_text(build_help_screen()))
        self.assertEqual(kwargs["parse_mode"], "HTML")
        self.assertEqual(refresh, [(42, 7)])


if __name__ == "__main__":
    unittest.main()
