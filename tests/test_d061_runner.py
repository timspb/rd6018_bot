"""Pure offline tests for the portable D061 host transport."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import d061_transport_windows as staging


class D061RunnerTests(unittest.TestCase):
    def test_current_and_legacy_sftp_profile_names(self):
        profiles=[
            ({'SFTP_RD6018_BOT_104_HOST':'node104.example','SFTP_RD6018_BOT_104_USER':'operator',
              'SFTP_RD6018_BOT_104_KNOWN_HOSTS':'known_hosts','SFTP_RD6018_BOT_104_PRIVATE_KEY_PATH':'node.key'},
             ('node104.example','operator','node.key')),
            ({'SFTP_HOST':'legacy.example','SFTP_USERNAME':'legacy-user',
              'SFTP_KNOWN_HOSTS':'known_hosts','SFTP_KEY_FILENAME':'legacy.key'},
             ('legacy.example','legacy-user','legacy.key')),
        ]
        for raw,expected in profiles:
            with self.subTest(raw=tuple(raw)),patch.object(staging,'SECRETS',Path('fixture.env')),patch.object(
                Path,'is_file',return_value=True),patch.object(staging,'dotenv_values',return_value=raw):
                result=staging.profile_values()
                self.assertEqual((result['SFTP_HOST'],result['SFTP_USERNAME'],
                                  result['SFTP_KEY_FILENAME']),expected)

    def test_unconfigured_profile_fails_closed(self):
        with patch.object(staging,'SECRETS',Path('missing.env')),patch.object(Path,'is_file',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'not configured'):
                staging.profile_values()

    def test_pinned_transport_has_no_hardware_actions_at_import(self):
        self.assertEqual(staging.SHA,'594a386e2b9fdd6bde9ebb15a5dfab30155291d6')
        self.assertEqual(staging.SERVICE,'rd6018-bot.service')
        self.assertFalse(Path(staging.CANDIDATE).is_dir())
