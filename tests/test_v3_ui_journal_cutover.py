from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

from application.journal_read_service import EventJournalReadService
from runtime.ui.actions import UIAction
from runtime.ui.components.journal import render_journal_text
from runtime.ui.models import JournalView
from runtime.ui.screen import ScreenId
from runtime.ui.screens.journal import build_journal_screen, journal_button_spec
from runtime.ui.telegram.journal import (
    HOME_CALLBACK_DATA,
    JOURNAL_CALLBACK_DATA,
    install_journal_screen,
)
from runtime.ui.telegram.renderer import action_from_callback_data, render_button
from telegram_panel import _is_workspace_callback


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


class _Bot:
    def __init__(self) -> None:
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class _Message:
    def __init__(self, *, fail_edit: bool = False) -> None:
        self.chat = SimpleNamespace(id=10)
        self.from_user = SimpleNamespace(id=7)
        self.message_id = 20
        self.fail_edit = fail_edit
        self.edits = []
        self.answers = []

    async def edit_text(self, text, **kwargs):
        if self.fail_edit:
            raise RuntimeError("photo message cannot become text")
        self.edits.append((text, kwargs))

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return SimpleNamespace(message_id=99)


class _Call:
    def __init__(self, *, fail_edit: bool = False) -> None:
        self.from_user = SimpleNamespace(id=7)
        self.message = _Message(fail_edit=fail_edit)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Interface:
    async def get_event_journal(self, limit=50):
        assert limit == 50
        return JournalView((
            "[2026-10-04 10:00:00] | Main Charge | 14.40V | 2.00A | 25C | 1.0Ah | START | profile=EFB",
            "[2026-10-04 10:10:00] | Main Charge | 14.50V | 1.90A | 25C | 1.2Ah | WARNING_TEMP",
        ))


class _App:
    def __init__(self):
        self.router = _Router()
        self.ParseMode = SimpleNamespace(HTML="HTML")
        self.bot = _Bot()
        self.user_dashboard = {}
        self.chat_dashboard = {}

    async def _check_chat_and_respond(self, _call):
        return True


class V3JournalUICutoverTests(unittest.TestCase):
    def test_screen_and_button_are_declarative(self):
        screen = build_journal_screen(JournalView(("plain",)))
        self.assertEqual(screen.screen_id, ScreenId.JOURNAL)
        self.assertEqual(screen.title, "📝 Логи событий")
        self.assertEqual(screen.buttons[0][0].action, UIAction.OPEN_HOME)
        entry = journal_button_spec()
        self.assertEqual(entry.action, UIAction.OPEN_JOURNAL)
        self.assertEqual(entry.target_screen, ScreenId.JOURNAL.value)

    def test_callback_encoding_round_trip(self):
        button = render_button(journal_button_spec())
        self.assertEqual(button.callback_data, JOURNAL_CALLBACK_DATA)
        self.assertEqual(action_from_callback_data(button.callback_data), UIAction.OPEN_JOURNAL)
        self.assertEqual(HOME_CALLBACK_DATA, "ui:nav.home")

    def test_journal_formatter_preserves_established_operator_semantics(self):
        events = (
            "[2026-10-04 10:00:00] | Main Charge | 14.40V | 2.00A | 25C | 1.0Ah | START | profile=EFB",
            "[2026-10-04 10:05:00] | Main Charge | 14.45V | 1.90A | 25C | 1.1Ah | CHECKPOINT",
            "[2026-10-04 10:10:00] | Main Charge | 14.50V | 1.80A | 25C | 1.2Ah | STAGE_CHANGE | Main Charge -> Mix",
        )
        text = render_journal_text(events)
        self.assertIn("<b>📝 Логи событий</b>", text)
        self.assertIn("🏁", text)
        self.assertIn(">>", text)
        self.assertNotIn("CHECKPOINT", text)

    def test_application_reader_returns_data_only_view_and_fail_closed_error(self):
        reader = EventJournalReadService(lambda limit: [f"event-{limit}"])
        view = reader.read(7)
        self.assertEqual(view.events, ("event-7",))
        self.assertEqual(view.error, "")

        def broken(_limit):
            raise RuntimeError("synthetic read failure")

        failed = EventJournalReadService(broken).read(7)
        self.assertEqual(failed.events, ())
        self.assertIn("RuntimeError", failed.error)

    def test_canonical_ui_tree_has_no_historical_or_physical_imports_calls(self):
        forbidden_modules = {
            "runtime.v2_runtime",
            "charge_logic",
            "hass_api",
            "runtime_safety",
            "managed_runtime_safety",
            "runtime_safety_strict",
            "safe_output",
        }
        forbidden_calls = {
            "turn_on",
            "turn_off",
            "set_voltage",
            "set_current",
            "set_ovp",
            "set_ocp",
            "safe_enable_output",
        }
        violations = []
        for path in sorted((ROOT / "runtime" / "ui").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_modules:
                            violations.append((path.name, "import", alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "") in forbidden_modules:
                        violations.append((path.name, "import", node.module))
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append((path.name, "call", node.func.attr))
        self.assertEqual([], violations)

    def test_historical_logs_routes_are_removed_and_command_is_canonical(self):
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        canonical = (ROOT / "runtime" / "ui" / "telegram" / "journal.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "logs"', source)
        self.assertNotIn('Command("logs")', source)
        self.assertNotIn("async def logs_handler", source)
        self.assertNotIn("async def cmd_logs", source)
        self.assertNotIn("def _build_logs_text(", source)
        self.assertIn('Command("logs")', canonical)
        self.assertIn("view = await interface.get_event_journal(50)", canonical)
        self.assertIn("build_journal_screen(view, shown=25)", canonical)

    def test_live_graph_toolbar_no_longer_constructs_raw_logs_callback(self):
        source = (ROOT / "operator_dashboard.py").read_text(encoding="utf-8")
        runtime_source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        polish_source = (ROOT / "ui_polish.py").read_text(encoding="utf-8")
        self.assertNotIn('callback_data="logs"', source)
        self.assertNotIn('callback_data="logs"', runtime_source)
        self.assertNotIn('callback_data="logs"', polish_source)
        self.assertIn("journal_button_spec()", source)
        self.assertIn("JOURNAL_CALLBACK_DATA", runtime_source)
        self.assertIn("JOURNAL_CALLBACK_DATA", polish_source)
        self.assertTrue(_is_workspace_callback(JOURNAL_CALLBACK_DATA))
        self.assertFalse(_is_workspace_callback("logs"))

    def test_production_composition_installs_journal_after_read_model(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        provider_pos = source.index(
            "operator_interface = OperatorSnapshotProvider("
        )
        journal_pos = source.index("install_journal_screen(")
        self.assertLess(provider_pos, journal_pos)
        self.assertIn("operator_read_source = OperatorReadSource(_legacy)", source)
        self.assertIn("interface=operator_interface", source)
        self.assertNotIn("OperatorSnapshotProvider(_legacy)", source)
        self.assertIn("home_handler=_legacy._operator_home_handler", source)


class V3JournalTelegramRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_canonical_handler_edits_text_workspace(self):
        app = _App()
        retired = []
        home_calls = []

        async def home(call):
            home_calls.append(call)

        install_journal_screen(
            app,
            interface=_Interface(),
            home_handler=home,
            retire_graph_tracking=lambda chat, user, message: retired.append((chat, user, message)),
        )
        call = _Call()
        await app._v3_journal_handler(call)

        self.assertEqual(retired, [(10, 7, 20)])
        self.assertEqual(app.user_dashboard[7], 20)
        self.assertEqual(app.chat_dashboard[10], 20)
        text, kwargs = call.message.edits[0]
        self.assertIn("Логи событий", text)
        back = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, HOME_CALLBACK_DATA)

        await app._v3_home_handler(call)
        self.assertEqual(home_calls, [call])

    async def test_logs_command_uses_same_canonical_journal_screen(self):
        app = _App()

        async def home(_call):
            return None

        install_journal_screen(
            app,
            interface=_Interface(),
            home_handler=home,
            retire_graph_tracking=lambda *_args: None,
        )
        message = _Message()
        command_handler = app.router.message.handlers[0]
        await command_handler(message)

        self.assertEqual(app.user_dashboard[7], 99)
        self.assertEqual(app.chat_dashboard[10], 99)
        text, kwargs = message.answers[0]
        self.assertIn("Логи событий", text)
        back = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, HOME_CALLBACK_DATA)

    async def test_photo_workspace_fallback_replaces_message_and_retires_old(self):
        app = _App()

        async def home(_call):
            return None

        install_journal_screen(
            app,
            interface=_Interface(),
            home_handler=home,
            retire_graph_tracking=lambda *_args: None,
        )
        call = _Call(fail_edit=True)
        await app._v3_journal_handler(call)

        self.assertEqual(app.user_dashboard[7], 99)
        self.assertEqual(app.chat_dashboard[10], 99)
        self.assertEqual(app.bot.deleted, [(10, 20)])
        self.assertEqual(len(call.message.answers), 1)


if __name__ == "__main__":
    unittest.main()
