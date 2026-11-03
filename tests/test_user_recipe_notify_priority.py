import unittest
from unittest.mock import patch
from runtime import production_runtime as runtime


class NotificationPriorityTests(unittest.TestCase):
    def test_explicit_recipient_overrides_last_active_chat(self):
        saved = (runtime.last_chat_id, runtime.last_notification_signature,
                 runtime.last_notification_at)
        try:
            runtime.last_chat_id = -2002
            runtime.last_notification_signature = ""
            runtime.last_notification_at = 0
            scheduled = []
            def capture(coro):
                scheduled.append(coro)
                coro.close()
            with patch.object(runtime, "NOTIFY_CHAT_ID", -3003), \
                 patch.object(runtime.asyncio, "create_task", side_effect=capture):
                runtime._charge_notify("recipe-fault-test")
                self.assertEqual(runtime.last_chat_id, -3003)
                self.assertEqual(len(scheduled), 1)
        finally:
            runtime.last_chat_id, runtime.last_notification_signature, \
                runtime.last_notification_at = saved
