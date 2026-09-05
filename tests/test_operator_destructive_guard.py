import types
import unittest

from operator_confirmation import ConfirmationStore
from operator_destructive_guard import DestructiveCallbackGuard, _observer_stop_token


class FakeCall:
    def __init__(self, data: str, *, chat_id: int = 100, user_id: int = 7):
        self.data = data
        self.message = types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id))
        self.from_user = types.SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeObserver:
    def __init__(self, *, started_at_s: float = 100.0, state: str = "active"):
        self.started_at_s = started_at_s
        self.state = types.SimpleNamespace(value=state)


class OperatorDestructiveGuardTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self):
        return types.SimpleNamespace(
            rd_control_mode_manager=types.SimpleNamespace(hands_off=True),
            rd_live_mix_observer=FakeObserver(),
        )

    async def test_execute_without_fresh_confirmation_is_non_actuating(self):
        app = self.make_app()
        guard = DestructiveCallbackGuard(app)
        calls = []

        async def handler(event, data):
            calls.append(event.data)

        event = FakeCall("operator_adopted_stop_execute")
        await guard(handler, event, {})

        self.assertEqual(calls, [])
        self.assertTrue(event.answers)

    async def test_confirm_then_execute_allows_exact_same_observer_once(self):
        app = self.make_app()
        store = ConfirmationStore(ttl_s=300.0)
        guard = DestructiveCallbackGuard(app, confirmations=store)
        calls = []

        async def handler(event, data):
            calls.append(event.data)

        confirm = FakeCall("operator_adopted_stop")
        await guard(handler, confirm, {})
        execute = FakeCall("operator_adopted_stop_execute")
        await guard(handler, execute, {})
        replay = FakeCall("operator_adopted_stop_execute")
        await guard(handler, replay, {})

        self.assertEqual(calls, ["operator_adopted_stop", "operator_adopted_stop_execute"])
        self.assertTrue(replay.answers)

    async def test_replacement_observer_invalidates_old_confirmation(self):
        app = self.make_app()
        guard = DestructiveCallbackGuard(app)
        calls = []

        async def handler(event, data):
            calls.append(event.data)

        await guard(handler, FakeCall("operator_adopted_stop"), {})
        app.rd_live_mix_observer = FakeObserver(started_at_s=200.0)
        execute = FakeCall("operator_adopted_stop_execute")
        await guard(handler, execute, {})

        self.assertEqual(calls, ["operator_adopted_stop"])
        self.assertTrue(execute.answers)

    async def test_confirmation_cannot_cross_chat(self):
        app = self.make_app()
        guard = DestructiveCallbackGuard(app)
        calls = []

        async def handler(event, data):
            calls.append((event.data, event.message.chat.id))

        await guard(handler, FakeCall("operator_adopted_stop", chat_id=100), {})
        wrong_chat = FakeCall("operator_adopted_stop_execute", chat_id=200)
        await guard(handler, wrong_chat, {})
        right_chat = FakeCall("operator_adopted_stop_execute", chat_id=100)
        await guard(handler, right_chat, {})

        self.assertEqual(
            calls,
            [
                ("operator_adopted_stop", 100),
                ("operator_adopted_stop_execute", 100),
            ],
        )
        self.assertTrue(wrong_chat.answers)

    async def test_observer_change_during_confirmation_prompt_leaves_no_grant(self):
        app = self.make_app()
        guard = DestructiveCallbackGuard(app)

        async def confirm_handler(event, data):
            app.rd_live_mix_observer = FakeObserver(started_at_s=300.0)

        await guard(confirm_handler, FakeCall("operator_adopted_stop"), {})
        execute = FakeCall("operator_adopted_stop_execute")
        called = []

        async def execute_handler(event, data):
            called.append(True)

        await guard(execute_handler, execute, {})
        self.assertEqual(called, [])
        self.assertTrue(execute.answers)

    def test_token_requires_hands_off_and_live_observer(self):
        app = self.make_app()
        token = _observer_stop_token(app)
        self.assertIsNotNone(token)

        app.rd_control_mode_manager.hands_off = False
        self.assertIsNone(_observer_stop_token(app))
        app.rd_control_mode_manager.hands_off = True
        app.rd_live_mix_observer.state = types.SimpleNamespace(value="completed")
        self.assertIsNone(_observer_stop_token(app))


if __name__ == "__main__":
    unittest.main()
