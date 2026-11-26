import unittest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery
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
        # PanelLastMiddleware restores L2; the handler only acknowledges.
        self.assertEqual(app._refreshed, [])
        self.assertEqual(app.bot.deleted, [])

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

