from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from application.journal_read_service import EventJournalReadService
import charging_log
from runtime.ui.actions import UIAction
from runtime.ui.components.journal import operator_journal_events, render_journal_text
from runtime.ui.models import JournalView
from runtime.ui.screen import ScreenId
from runtime.ui.screens.journal import build_journal_screen, journal_button_spec
from runtime.ui.telegram.journal import (
    HOME_CALLBACK_DATA,
    JOURNAL_CALLBACK_DATA,
    install_journal_screen,
)
from runtime.ui.telegram.renderer import action_from_callback_data, callback_data_for, render_button
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
    async def get_event_journal(self, limit=None):
        assert limit is None
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
        self.assertIn("➡️", text)
        self.assertNotIn("CHECKPOINT", text)

    def test_long_journal_entries_are_bounded_with_visible_truncation_notice(self):
        event = "[2026-10-04 10:00:00] | Main Charge | 14.40V | 2.00A | 25C | 1.0Ah | " + "X" * 10000
        text = render_journal_text((event,))
        self.assertLess(len(text), 1200)
        self.assertIn("запись сокращена", text)

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

    def test_operator_journal_reader_keeps_every_current_session_line(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "charging_history.log"
            log_path.write_text(
                "[2026-10-03 09:00:00] | Main Charge | 14.4 | 2 | 25 | 1 | SESSION_START | id=old\n"
                "[2026-10-03 10:00:00] | Main Charge | 14.4 | 2 | 25 | 1 | CHECKPOINT | old\n"
                "[2026-10-04 10:00:00] | Main Charge | 14.4 | 2 | 25 | 1 | SESSION_START | id=current\n"
                "[2026-10-04 10:10:00] | Main Charge | 14.4 | 2 | 25 | 1 | CHECKPOINT\n"
                "[2026-10-04 10:11:00] | Main Charge | 14.5 | 1 | 25 | 1 | STAGE_CHANGE | Main -> Mix\n",
                encoding="utf-8",
            )
            with patch.object(charging_log, "LOG_FILE", str(log_path)):
                view = EventJournalReadService().read(None)
        self.assertEqual(len(view.events), 3)
        self.assertIn("CHECKPOINT", view.events[1])
        self.assertNotIn("old", "\n".join(view.events))
        self.assertEqual(view.error, "")

    def test_async_journal_read_does_not_block_event_loop(self):
        async def scenario():
            reader = EventJournalReadService(lambda _limit: ["event"])
            ticked = asyncio.Event()
            async def tick():
                await asyncio.sleep(0.01)
                ticked.set()
            task = asyncio.create_task(tick())
            async def delegated_read(function, limit):
                await asyncio.sleep(0.03)
                return function(limit)
            offload = AsyncMock(side_effect=delegated_read)
            with patch("application.journal_read_service.asyncio.to_thread", new=offload):
                view = await reader.aread(None)
            self.assertTrue(ticked.is_set())
            self.assertEqual(view.events, ("event",))
            offload.assert_called_once_with(reader.read, None)
            await task
        asyncio.run(scenario())

    def test_journal_screen_paginates_bounded_pages_and_keeps_back(self):
        view = JournalView(tuple(f"event-{index}" for index in range(9)))
        screen = build_journal_screen(view, page_size=2)
        self.assertIn("События 8–9 из 9", screen.body)
        self.assertEqual(screen.buttons[0][0].label, "⬅ Старее")
        self.assertEqual(screen.buttons[-1][0].action, UIAction.OPEN_HOME)
        older = build_journal_screen(view, offset=2, page_size=2)
        labels = [row[0].label for row in older.buttons]
        self.assertEqual(labels, ["⬅ Старее", "Новее ➡", "⬅ К панели"])

    def test_stale_pagination_offset_clamps_to_oldest_available_event(self):
        view = JournalView(tuple(
            f"[2026-10-04 10:00:0{index}] | Main Charge | 14.4 | 1 | 25 | 1 | DONE"
            for index in range(3)
        ))
        screen = build_journal_screen(view, offset=100_000, page_size=2)
        self.assertIn("События 1–1 из 3", screen.body)
        self.assertNotIn("1–0", screen.body)

    def test_service_rows_are_removed_before_pagination_and_counting(self):
        events = (
            "[2026-10-04 10:00:00] | MAIN | 14.4 | 2 | 25 | 0 | SESSION_START | profile=EFB",
            "[2026-10-04 10:01:00] | MAIN | 14.4 | 2 | 25 | 0 | CHECKPOINT",
            "[2026-10-04 10:02:00] | MAIN | 14.4 | 2 | 25 | 0 | RESTORE",
            "[2026-10-04 10:03:00] | MAIN | 14.4 | 1 | 25 | 1 | WARNING_35C",
            "[2026-10-04 10:04:00] | MIX | 14.4 | 1 | 25 | 1 | STAGE_CHANGE | MAIN -> MIX",
        )
        self.assertEqual(len(operator_journal_events(events)), 3)
        newest = build_journal_screen(JournalView(events), page_size=2)
        self.assertIn("События 2–3 из 3", newest.body)
        self.assertIn("Переход этапа", newest.body)
        older = build_journal_screen(JournalView(events), offset=2, page_size=2)
        self.assertIn("События 1–1 из 3", older.body)
        self.assertIn("Заряд запущен", older.body)
        self.assertNotIn("CHECKPOINT", newest.body + older.body)
        self.assertNotIn("RESTORE", newest.body + older.body)

    def test_human_event_lines_are_single_line_escaped_and_include_readings(self):
        event = (
            '[2026-10-04 10:00:00] | DESULFATION | 14.40V | 2.00A | 35.0C | '
            '1.0Ah | WARNING_TEMP <critical> & check'
        )
        text = render_journal_text((event,))
        self.assertEqual(len(text.splitlines()), 2)
        self.assertIn("Восстановление", text)
        self.assertIn("U 14.40V · I 2.00A · T 35.0C", text)
        self.assertIn("&lt;critical&gt; &amp; check", text)
        self.assertNotIn("<critical>", text)

    def test_unrecorded_finish_evidence_is_not_invented(self):
        event = "[2026-10-04 10:00:00] | MIX | 14.4 | 1 | 25 | 1 | MIX_CV_DELTA_WAIT"
        text = render_journal_text((event,))
        self.assertIn("Mix cv delta wait", text)
        self.assertNotIn("Подтверждён Delta", text)
        self.assertNotIn("Imin", text)

    def test_recorded_finish_hold_evidence_is_presented_as_confirmed_delta(self):
        event = (
            "[2026-10-04 10:00:00] | MIX | 14.4 | 0.5 | 25 | 1 | "
            "V2_FINISH_HOLD_START | Imin=0.500А, ΔI=0.300А"
        )
        text = render_journal_text((event,))
        self.assertIn("Delta подтверждён; началась финишная выдержка", text)
        self.assertIn("Imin=0.500А, ΔI=0.300А", text)

    def test_worst_case_page_stays_below_telegram_4096_character_limit(self):
        hostile = "[2026-10-04 10:00:00] | Main Charge | " + ">" * 400
        view = JournalView((hostile,) * 12)
        screen = build_journal_screen(view, page_size=12)
        from runtime.ui.telegram.renderer import render_screen_text
        rendered = render_screen_text(screen)
        self.assertLessEqual(len(rendered), 4096)
        self.assertIn("запись сокращена", rendered)

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
        self.assertIn("view = await interface.get_event_journal(None)", canonical)
        self.assertIn("build_journal_screen(view, offset=offset)", canonical)

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
        self.assertIn("operator_read_source = OperatorReadSource(app)", source)
        self.assertIn("interface=operator_interface", source)
        self.assertNotIn("OperatorSnapshotProvider(app)", source)
        self.assertIn("home_handler=app._operator_home_handler", source)


class V3JournalTelegramRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_journal_workspace_does_not_append_dashboard(self):
        app = _App()
        retired = []
        home_calls = []
        restore_calls = []

        async def home(call):
            home_calls.append(call)

        async def restore(chat_id, user_id):
            restore_calls.append((chat_id, user_id))
            app.user_dashboard[user_id] = 101
            app.chat_dashboard[chat_id] = 101

        install_journal_screen(
            app,
            interface=_Interface(),
            home_handler=home,
            retire_graph_tracking=lambda chat, user, message: retired.append((chat, user, message)),
            restore_dashboard=restore,
        )
        call = _Call()
        call.data = JOURNAL_CALLBACK_DATA
        await app._v3_journal_handler(call)

        self.assertEqual(retired, [])
        self.assertEqual(restore_calls, [])
        self.assertEqual(app.user_dashboard, {})
        self.assertEqual(app.chat_dashboard, {})
        text, kwargs = call.message.answers[0]
        self.assertIn("Логи событий", text)
        back = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, HOME_CALLBACK_DATA)

        await app._v3_home_handler(call)
        self.assertEqual(home_calls, [call])

    async def test_logs_command_keeps_dashboard_identity_separate(self):
        app = _App()

        async def home(_call):
            return None

        async def restore(chat_id, user_id):
            app.user_dashboard[user_id] = 101
            app.chat_dashboard[chat_id] = 101

        install_journal_screen(
            app,
            interface=_Interface(),
            home_handler=home,
            retire_graph_tracking=lambda *_args: None,
            restore_dashboard=restore,
        )
        message = _Message()
        command_handler = app.router.message.handlers[0]
        await command_handler(message)

        self.assertEqual(app.user_dashboard, {})
        self.assertEqual(app.chat_dashboard, {})
        text, kwargs = message.answers[0]
        self.assertIn("Логи событий", text)
        back = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(back.callback_data, HOME_CALLBACK_DATA)

    async def test_photo_workspace_is_not_edited_into_journal(self):
        app = _App()

        async def home(_call):
            return None

        async def restore(chat_id, user_id):
            app.user_dashboard[user_id] = 101
            app.chat_dashboard[chat_id] = 101

        install_journal_screen(
            app,
            interface=_Interface(),
            home_handler=home,
            retire_graph_tracking=lambda *_args: None,
            restore_dashboard=restore,
        )
        call = _Call(fail_edit=True)
        call.data = JOURNAL_CALLBACK_DATA
        await app._v3_journal_handler(call)

        self.assertEqual(app.user_dashboard, {})
        self.assertEqual(app.chat_dashboard, {})
        self.assertEqual(app.bot.deleted, [])
        self.assertEqual(len(call.message.answers), 1)
        self.assertEqual(call.message.edits, [])

    async def test_pagination_edits_only_journal_and_does_not_recreate_dashboard(self):
        app = _App()

        async def home(_call):
            return None

        async def restore(*_args):
            self.fail("pagination must not disturb the dashboard")

        install_journal_screen(
            app, interface=_Interface(), home_handler=home,
            restore_dashboard=restore,
        )
        call = _Call()
        call.data = callback_data_for(UIAction.OPEN_JOURNAL, (("offset", "4"),))
        await app._v3_journal_handler(call)
        self.assertEqual(len(call.message.edits), 1)
        self.assertEqual(call.message.answers, [])
        self.assertEqual(app.user_dashboard, {})

    async def test_stale_photo_pagination_sends_page_instead_of_silently_dropping_it(self):
        app = _App()
        async def home(_call):
            return None
        interface = _Interface()
        install_journal_screen(app, interface=interface, home_handler=home)
        call = _Call(fail_edit=True)
        call.data = callback_data_for(UIAction.OPEN_JOURNAL, (("offset", "2"),))
        await app._v3_journal_handler(call)
        self.assertEqual(len(call.message.answers), 1)
        self.assertIn("Логи событий", call.message.answers[0][0])
        self.assertEqual(call.answers, [((), {})])

    async def test_route_read_error_is_acknowledged_and_reported(self):
        app = _App()
        class BrokenInterface:
            async def get_event_journal(self, _limit=None):
                raise OSError("journal unavailable")
        async def home(_call):
            return None
        install_journal_screen(app, interface=BrokenInterface(), home_handler=home)
        call = _Call()
        call.data = JOURNAL_CALLBACK_DATA
        await app._v3_journal_handler(call)
        self.assertTrue(call.answers)
        self.assertTrue(call.message.answers)


if __name__ == "__main__":
    unittest.main()
