import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.enums import ChatType, MessageEntityType
from aiogram.methods import DeleteMessage, SendMessage, SendPhoto
from aiogram.types import Chat, Message, MessageEntity, Update, User

import bot as app


class TelegramStartDispatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The synthetic private chat is explicitly authorized for this dispatcher
        # test; otherwise the access guard returns before exercising /start.
        app.ALLOWED_CHAT_IDS = ()
        app.user_dashboard.clear()
        app.chat_dashboard.clear()
        manager = app.terminal_panel_manager
        manager._panel_by_chat.clear()
        manager._workspace_chats.clear()
        if app.router.parent_router is None:
            app.dp.include_router(app.router)

    @staticmethod
    def _start_update() -> Update:
        return Update(
            update_id=7001,
            message=Message(
                message_id=501,
                date=datetime.now(timezone.utc),
                chat=Chat(id=1, type=ChatType.PRIVATE),
                from_user=User(id=1, is_bot=False, first_name="Operator"),
                text="/start",
                entities=[
                    MessageEntity(
                        type=MessageEntityType.BOT_COMMAND,
                        offset=0,
                        length=6,
                    )
                ],
            ),
        )

    @staticmethod
    def _read_only_dashboard_patches():
        return (
            patch.object(app.hass, "get_all_live", new=AsyncMock(return_value={})),
            patch.object(
                app,
                "generate_chart",
                side_effect=AssertionError("ordinary dashboard must not render a chart"),
            ),
        )

    async def test_start_uses_text_dashboard_without_graph_render(self):
        """The ordinary /start dashboard must not enter Matplotlib/NumPy."""
        manager = app.terminal_panel_manager
        manager.adopt(chat_id=1, user_id=1, message_id=77)
        calls = []

        async def fake_telegram_api(_bot, method, *args, **kwargs):
            del args, kwargs
            calls.append(type(method).__name__)
            if isinstance(method, DeleteMessage):
                return True
            if isinstance(method, SendMessage):
                return SimpleNamespace(message_id=88)
            raise AssertionError(f"unexpected Telegram method: {type(method).__name__}")

        graph_live, graph_render = self._read_only_dashboard_patches()
        with (
            graph_live,
            graph_render,
            patch.object(Bot, "__call__", new=fake_telegram_api),
        ):
            await app.dp.feed_update(app.bot, self._start_update())

        self.assertNotIn("SendPhoto", calls)
        self.assertIn("SendMessage", calls)
        self.assertEqual(app.user_dashboard[1], 88)
        self.assertEqual(app.chat_dashboard[1], 88)
        self.assertEqual(manager.panel_id(1), 88)

    async def test_start_does_not_use_photo_compatibility_path(self):
        """The ordinary dashboard remains text-only after the migration."""
        manager = app.terminal_panel_manager
        manager.adopt(chat_id=1, user_id=1, message_id=77)
        calls = []

        async def fake_telegram_api(_bot, method, *args, **kwargs):
            del args, kwargs
            calls.append(type(method).__name__)
            if isinstance(method, DeleteMessage):
                return True
            if isinstance(method, SendPhoto):
                raise AssertionError("ordinary /start must not send a graph photo")
            if isinstance(method, SendMessage):
                return SimpleNamespace(message_id=89)
            raise AssertionError(f"unexpected Telegram method: {type(method).__name__}")

        graph_live, graph_render = self._read_only_dashboard_patches()
        with (
            graph_live,
            graph_render,
            patch.object(Bot, "__call__", new=fake_telegram_api),
        ):
            await app.dp.feed_update(app.bot, self._start_update())

        self.assertNotIn("SendPhoto", calls)
        self.assertIn("SendMessage", calls)
        self.assertEqual(app.user_dashboard[1], 89)
        self.assertEqual(app.chat_dashboard[1], 89)
        self.assertEqual(manager.panel_id(1), 89)

    async def test_start_preserves_primary_error_when_text_fallback_also_fails(self):
        """A total Telegram outage must not be converted into false handled success."""
        manager = app.terminal_panel_manager
        manager.adopt(chat_id=1, user_id=1, message_id=77)
        calls = []

        async def fake_telegram_api(_bot, method, *args, **kwargs):
            del args, kwargs
            calls.append(type(method).__name__)
            if isinstance(method, DeleteMessage):
                return True
            if isinstance(method, SendMessage):
                raise RuntimeError("synthetic sendMessage rejection")
            raise AssertionError(f"unexpected Telegram method: {type(method).__name__}")

        graph_live, graph_render = self._read_only_dashboard_patches()
        with (
            graph_live,
            graph_render,
            patch.object(Bot, "__call__", new=fake_telegram_api),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic sendMessage rejection"):
                await app.dp.feed_update(app.bot, self._start_update())

        self.assertIn("SendMessage", calls)
        self.assertEqual(manager.panel_id(1), 77)

    async def test_charge_workspace_replaces_stale_message_and_updates_reference(self):
        class StaleMessage:
            message_id = 77
            chat = SimpleNamespace(id=1)

            async def edit_caption(self, **kwargs):
                raise RuntimeError("message to edit not found")

            async def edit_text(self, *args, **kwargs):
                raise RuntimeError("message to edit not found")

        class ReplacementBot:
            def __init__(self):
                self.deleted = []
                self.sent = []

            async def delete_message(self, chat_id, message_id):
                self.deleted.append((chat_id, message_id))

            async def send_message(self, chat_id, text, **kwargs):
                self.sent.append((chat_id, text, kwargs))
                return SimpleNamespace(message_id=88)

        old_bot = app.bot
        old_user_dashboard = dict(app.user_dashboard)
        old_chat_dashboard = dict(app.chat_dashboard)
        replacement_bot = ReplacementBot()
        app.bot = replacement_bot
        app.user_dashboard.clear()
        app.chat_dashboard.clear()
        try:
            call = SimpleNamespace(
                message=StaleMessage(),
                from_user=SimpleNamespace(id=9),
            )
            result = await app._edit_or_send_charge_workspace(
                call,
                "<b>Режимы</b>",
                SimpleNamespace(),
            )
            replacement_user_dashboard = dict(app.user_dashboard)
            replacement_chat_dashboard = dict(app.chat_dashboard)
        finally:
            app.bot = old_bot
            app.user_dashboard.clear()
            app.user_dashboard.update(old_user_dashboard)
            app.chat_dashboard.clear()
            app.chat_dashboard.update(old_chat_dashboard)

        self.assertEqual(result, 88)
        self.assertEqual(replacement_bot.deleted, [(1, 77)])
        self.assertEqual(len(replacement_bot.sent), 1)
        self.assertEqual(replacement_user_dashboard, {9: 88})
        self.assertEqual(replacement_chat_dashboard, {1: 88})

    async def test_charge_workspace_preserves_edit_failure_as_send_failure(self):
        class StaleMessage:
            message_id = 77
            chat = SimpleNamespace(id=1)

            async def edit_caption(self, **kwargs):
                raise RuntimeError("message to edit not found")

            async def edit_text(self, *args, **kwargs):
                raise RuntimeError("message to edit not found")

        class FailingBot:
            async def delete_message(self, chat_id, message_id):
                return None

            async def send_message(self, *args, **kwargs):
                raise RuntimeError("Telegram unavailable")

        old_bot = app.bot
        app.bot = FailingBot()
        try:
            call = SimpleNamespace(
                message=StaleMessage(),
                from_user=SimpleNamespace(id=9),
            )
            with self.assertRaisesRegex(RuntimeError, "Telegram unavailable"):
                await app._edit_or_send_charge_workspace(
                    call,
                    "<b>Режимы</b>",
                    SimpleNamespace(),
                )
        finally:
            app.bot = old_bot


if __name__ == "__main__":
    unittest.main()
