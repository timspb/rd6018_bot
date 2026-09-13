import io
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

    async def test_start_recovers_to_text_when_graph_delivery_fails(self):
        """Exercise real Dispatcher -> /start -> final graph dashboard transport.

        A deterministic media-delivery failure must not leave the operator with no
        response after the legacy handler has retired the previous dashboard.
        """
        manager = app.terminal_panel_manager
        manager.adopt(chat_id=1, user_id=1, message_id=77)
        calls = []

        async def fake_telegram_api(_bot, method, *args, **kwargs):
            del args, kwargs
            calls.append(type(method).__name__)
            if isinstance(method, DeleteMessage):
                return True
            if isinstance(method, SendPhoto):
                raise RuntimeError("synthetic sendPhoto rejection")
            if isinstance(method, SendMessage):
                return SimpleNamespace(message_id=88)
            raise AssertionError(f"unexpected Telegram method: {type(method).__name__}")

        with (
            patch.object(app, "_chat_allowed", return_value=True),
            patch.object(app.hass, "get_all_live", new=AsyncMock(return_value={})),
            patch.object(
                app,
                "get_graph_data_with_temp",
                new=AsyncMock(return_value=([1.0], [12.5], [0.2], [25.0])),
            ),
            patch.object(app, "generate_chart", return_value=io.BytesIO(b"synthetic-png")),
            patch.object(Bot, "__call__", new=fake_telegram_api),
        ):
            await app.dp.feed_update(app.bot, self._start_update())

        self.assertIn("SendPhoto", calls)
        self.assertIn("SendMessage", calls)
        self.assertEqual(app.user_dashboard[1], 88)
        self.assertEqual(app.chat_dashboard[1], 88)
        self.assertEqual(manager.panel_id(1), 88)


if __name__ == "__main__":
    unittest.main()
