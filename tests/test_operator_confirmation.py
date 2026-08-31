import types
import unittest

from operator_confirmation import ConfirmationStore


class FakeCall:
    def __init__(self, *, chat_id: int, user_id: int):
        self.message = types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id))
        self.from_user = types.SimpleNamespace(id=user_id)


class OperatorConfirmationTests(unittest.TestCase):
    def test_fresh_confirmation_is_one_shot(self):
        store = ConfirmationStore(ttl_s=300.0)
        store.issue(chat_id=100, user_id=7, token="auto:session-a", now=10.0)

        self.assertEqual(
            store.consume(chat_id=100, user_id=7, now=309.9),
            "auto:session-a",
        )
        self.assertIsNone(store.consume(chat_id=100, user_id=7, now=309.9))

    def test_confirmation_is_bound_to_chat_and_user(self):
        store = ConfirmationStore(ttl_s=300.0)
        store.issue(chat_id=100, user_id=7, token="manual:1", now=10.0)

        self.assertIsNone(store.consume(chat_id=200, user_id=7, now=20.0))
        self.assertIsNone(store.consume(chat_id=100, user_id=8, now=20.0))
        self.assertEqual(
            store.consume(chat_id=100, user_id=7, now=20.0),
            "manual:1",
        )

    def test_expired_or_clock_reversed_confirmation_fails_closed_and_is_consumed(self):
        store = ConfirmationStore(ttl_s=300.0)
        store.issue(chat_id=100, user_id=7, token="auto:old", now=10.0)
        self.assertIsNone(store.consume(chat_id=100, user_id=7, now=310.001))
        self.assertIsNone(store.consume(chat_id=100, user_id=7, now=20.0))

        store.issue(chat_id=100, user_id=7, token="auto:clock", now=50.0)
        self.assertIsNone(store.consume(chat_id=100, user_id=7, now=49.0))
        self.assertIsNone(store.consume(chat_id=100, user_id=7, now=51.0))

    def test_callback_helpers_keep_confirmation_in_originating_chat(self):
        store = ConfirmationStore(ttl_s=300.0)
        origin = FakeCall(chat_id=-100123, user_id=7)
        other_chat = FakeCall(chat_id=-100999, user_id=7)

        self.assertTrue(store.issue_for_call(origin, "auto:session-a", now=10.0))
        self.assertIsNone(store.consume_for_call(other_chat, now=20.0))
        self.assertEqual(
            store.consume_for_call(origin, now=20.0),
            "auto:session-a",
        )

    def test_invalid_ttl_is_rejected(self):
        for ttl in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(ttl=ttl):
                with self.assertRaises(ValueError):
                    ConfirmationStore(ttl_s=ttl)


if __name__ == "__main__":
    unittest.main()
