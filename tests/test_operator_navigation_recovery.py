import types
import unittest

from operator_navigation_recovery import install_operator_navigation_recovery


class DummyCallbackRegistry:
    def __call__(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


class DummyRouter:
    def __init__(self):
        self.callback_query = DummyCallbackRegistry()


class DummyBot:
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class DummyCall:
    def __init__(self, *, message_id=200):
        self.from_user = types.SimpleNamespace(id=7)
        self.message = types.SimpleNamespace(
            message_id=message_id,
            chat=types.SimpleNamespace(id=11),
        )
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class OperatorNavigationRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app():
        refreshed = []

        async def check_chat_and_respond(call):
            return True

        app = types.SimpleNamespace(
            router=DummyRouter(),
            bot=DummyBot(),
            user_dashboard={7: 100},
            chat_dashboard={11: 100},
            _check_chat_and_respond=check_chat_and_respond,
        )

        async def refresh(chat_id, user_id, message_id):
            refreshed.append((chat_id, user_id, message_id))

        app._refresh_operator_panel = refresh
        app._refreshed = refreshed
        return app

    async def test_back_deletes_detail_message_and_refreshes_existing_panel(self):
        app = self._app()
        install_operator_navigation_recovery(app)
        call = DummyCall(message_id=200)

        await app._operator_home_handler(call)

        self.assertEqual(app.bot.deleted, [(11, 200)])
        self.assertEqual(app._refreshed, [(11, 7, 100)])
        self.assertTrue(call.answers)

    async def test_back_on_dashboard_refreshes_same_message_without_delete(self):
        app = self._app()
        install_operator_navigation_recovery(app)
        call = DummyCall(message_id=100)

        await app._operator_home_handler(call)

        self.assertEqual(app.bot.deleted, [])
        self.assertEqual(app._refreshed, [(11, 7, 100)])


if __name__ == "__main__":
    unittest.main()
