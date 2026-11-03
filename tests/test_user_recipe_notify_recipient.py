import unittest
from unittest.mock import patch
import config


class NotificationRecipientTests(unittest.TestCase):
    def test_explicit_negative_group_is_supported_when_allowed(self):
        with patch.object(config, "ALLOWED_CHAT_IDS", (1001, -2002, -3003)):
            with patch.dict("os.environ", {"NOTIFY_CHAT_ID": "-2002"}):
                self.assertEqual(config._configured_notify_chat_id(), -2002)

    def test_unknown_target_is_not_selected(self):
        with patch.object(config, "ALLOWED_CHAT_IDS", (1001, -2002, -3003)):
            with patch.dict("os.environ", {"NOTIFY_CHAT_ID": "9999"}):
                self.assertIsNone(config._configured_notify_chat_id())

    def test_unset_and_invalid_target(self):
        with patch.object(config, "ALLOWED_CHAT_IDS", (1001,)):
            with patch.dict("os.environ", {"NOTIFY_CHAT_ID": "not-an-id"}):
                self.assertIsNone(config._configured_notify_chat_id())
            with patch.dict("os.environ", {"NOTIFY_CHAT_ID": ""}):
                self.assertIsNone(config._configured_notify_chat_id())
