import importlib
import os
import unittest
from unittest.mock import patch


class AuthConfigTests(unittest.TestCase):
    def _reload_config(self, env):
        with patch.dict(os.environ, env, clear=False):
            import config
            return importlib.reload(config)

    def test_empty_allowlist_is_fail_closed_by_default(self):
        with patch.dict(
            os.environ,
            {"ALLOWED_CHAT_IDS": "", "ALLOW_ALL_CHATS": "0"},
            clear=False,
        ):
            import config
            config = importlib.reload(config)
            self.assertEqual(config.ALLOWED_CHAT_IDS, (-1,))

    def test_allow_all_requires_explicit_override(self):
        with patch.dict(
            os.environ,
            {"ALLOWED_CHAT_IDS": "", "ALLOW_ALL_CHATS": "1"},
            clear=False,
        ):
            import config
            config = importlib.reload(config)
            self.assertEqual(config.ALLOWED_CHAT_IDS, ())

    def test_explicit_chat_ids_are_preserved(self):
        with patch.dict(
            os.environ,
            {"ALLOWED_CHAT_IDS": "123, 456", "ALLOW_ALL_CHATS": "0"},
            clear=False,
        ):
            import config
            config = importlib.reload(config)
            self.assertEqual(config.ALLOWED_CHAT_IDS, (123, 456))


if __name__ == "__main__":
    unittest.main()
