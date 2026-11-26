import unittest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import CallbackQuery
from runtime.ui.telegram.panel_lifecycle import TerminalPanelManager
from test_operator_navigation_recovery import (
    OperatorNavigationRecoveryTests, DummyCall,
)
from operator_navigation_recovery import install_operator_navigation_recovery


class StaleCallbackNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_callback_still_navigates_home(self):
        app = OperatorNavigationRecoveryTests._app()
        install_operator_navigation_recovery(app)
        call = DummyCall()
        async def stale(*args, **kwargs):
            raise TelegramBadRequest(
                method=AnswerCallbackQuery(callback_query_id="test"),
                message="Bad Request: query is too old and response timeout expired or query ID is invalid",
            )
        call.answer = stale
        await app._operator_home_handler(call)
        self.assertEqual(app._refreshed, [])
        self.assertEqual(app.bot.deleted, [])
        restores = []
        async def restore(chat_id, user_id):
            restores.append((chat_id, user_id))
            return 300
        app._restore_dashboard_to_bottom = restore
        lifecycle = TerminalPanelManager(app)
        event = CallbackQuery.model_validate({
            "id": "expired-query",
            "from": {"id": 7, "is_bot": False, "first_name": "operator"},
            "chat_instance": "test-chat",
            "message": {
                "message_id": 200,
                "date": 1764150000,
                "chat": {"id": 11, "type": "private"},
            },
            "data": "operator_done",
        })
        await lifecycle.after_event(event)
        self.assertEqual(restores, [(11, 7)])
        self.assertEqual(app.chat_dashboard[11], 300)
        self.assertEqual(app.user_dashboard[7], 300)

    async def test_unrelated_telegram_bad_request_is_not_swallowed(self):
        app = OperatorNavigationRecoveryTests._app()
        install_operator_navigation_recovery(app)
        call = DummyCall()
        async def bad(*args, **kwargs):
            raise TelegramBadRequest(
                method=AnswerCallbackQuery(callback_query_id="test"),
                message="Bad Request: chat not found",
            )
        call.answer = bad
        with self.assertRaises(TelegramBadRequest):
            await app._operator_home_handler(call)
        self.assertEqual(app._refreshed, [])

