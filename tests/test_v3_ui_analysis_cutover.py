from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from runtime.ui.actions import UIAction
from runtime.ui.screen import ScreenId
from runtime.ui.screens.analysis import analysis_button_spec, build_analysis_screen
from runtime.ui.telegram.analysis import (
    ANALYSIS_CALLBACK_DATA,
    HOME_CALLBACK_DATA,
    install_analysis_screen,
)
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
        self.callback_query = _RouterGroup()
        self.message = _RouterGroup()


class _Message:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=10)
        self.from_user = SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return SimpleNamespace(message_id=99)


class _Call:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=7)
        self.message = _Message()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _App:
    def __init__(self) -> None:
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")

    async def _check_chat_and_respond(self, _event):
        return True


class V3AnalysisUICutoverTests(unittest.TestCase):
    def test_analysis_screen_and_button_are_declarative(self):
        screen = build_analysis_screen("<b>🧠 AI Анализ</b>\nТестовый вывод")
        self.assertEqual(screen.screen_id, ScreenId.ANALYSIS)
        self.assertEqual(screen.title, "🧠 AI Анализ")
        self.assertEqual(render_screen_text(screen), "<b>🧠 AI Анализ</b>\n\nТестовый вывод")
        self.assertEqual(screen.buttons[0][0].action, UIAction.OPEN_HOME)

        button = analysis_button_spec()
        self.assertEqual(button.action, UIAction.OPEN_ANALYSIS)
        self.assertEqual(button.target_screen, ScreenId.ANALYSIS.value)
        self.assertEqual(ANALYSIS_CALLBACK_DATA, "ui:nav.analysis")
        self.assertEqual(HOME_CALLBACK_DATA, "ui:nav.home")

    def test_canonical_analysis_tree_has_no_historical_or_physical_imports(self):
        for rel in (
            "runtime/ui/screens/analysis.py",
            "runtime/ui/telegram/analysis.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            for forbidden in (
                "runtime.v2_runtime",
                "charge_logic",
                "hass_api",
                "ai_engine",
                "DeepSeek",
                "runtime_safety",
                "safe_output",
            ):
                self.assertNotIn(forbidden, source, f"{rel}: {forbidden}")

    def test_historical_ai_routes_and_raw_callbacks_are_removed(self):
        runtime_source = (ROOT / "runtime" / "v2_runtime.py").read_text(encoding="utf-8")
        operator_source = (ROOT / "operator_hmi.py").read_text(encoding="utf-8")
        panel_source = (ROOT / "telegram_panel.py").read_text(encoding="utf-8")
        self.assertNotIn('Command("ai")', runtime_source)
        self.assertNotIn('F.data == "ai_analysis"', runtime_source)
        self.assertNotIn("async def cmd_ai(", runtime_source)
        self.assertNotIn("async def ai_analysis_handler(", runtime_source)
        self.assertNotIn('callback_data="ai_analysis"', runtime_source)
        self.assertNotIn('callback_data="ai_analysis"', operator_source)
        self.assertNotIn('"ai_analysis"', panel_source)
        self.assertIn("ANALYSIS_CALLBACK_DATA", runtime_source)
        self.assertIn("ANALYSIS_CALLBACK_DATA", operator_source)
        self.assertIn("ANALYSIS_CALLBACK_DATA", panel_source)

    def test_composition_installs_analysis_with_injected_provider(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("install_analysis_screen(", source)
        self.assertIn("analysis_provider=_legacy._build_ai_analysis_text", source)
        self.assertIn("home_handler=_legacy._operator_home_handler", source)


class V3AnalysisTelegramRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_and_command_share_injected_provider(self):
        app = _App()
        provider_calls = []
        home_calls = []

        async def provider():
            provider_calls.append(True)
            return "<b>🧠 AI Анализ</b>\nРезультат"

        async def home(call):
            home_calls.append(call)

        install_analysis_screen(
            app,
            analysis_provider=provider,
            home_handler=home,
        )

        call = _Call()
        await app._v3_analysis_handler(call)
        self.assertEqual(provider_calls, [True])
        text, kwargs = call.message.answers[0]
        self.assertEqual(text, "<b>🧠 AI Анализ</b>\n\nРезультат")
        self.assertEqual(
            kwargs["reply_markup"].inline_keyboard[0][0].callback_data,
            HOME_CALLBACK_DATA,
        )

        command = app.router.message.handlers[0]
        message = _Message()
        await command(message)
        self.assertEqual(provider_calls, [True, True])
        self.assertEqual(message.answers[0][0], "<b>🧠 AI Анализ</b>\n\nРезультат")

        await app._v3_home_handler(call)
        self.assertEqual(home_calls, [call])


if __name__ == "__main__":
    unittest.main()
