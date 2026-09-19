import os
import unittest
from unittest.mock import patch

from application.live_observer_configuration import LiveObserverConfigurationCheck


class Workstream37LiveObserverConfigurationTests(unittest.TestCase):
    def test_missing_secrets_blocks_without_values(self):
        result = LiveObserverConfigurationCheck().check({})
        self.assertEqual("BLOCKED", result.status)
        self.assertEqual(("MISSING", "MISSING"), tuple(item.status for item in result.secret_checks))
        self.assertFalse(LiveObserverConfigurationCheck.safe_start_allowed(result))

    def test_configured_secrets_are_presence_only(self):
        result = LiveObserverConfigurationCheck().check({"HA_TOKEN": "secret-ha", "ESPHOME_API_KEY": "secret-esp"})
        self.assertEqual("LIVE_OBSERVER_CONFIGURATION_READY", result.status)
        self.assertTrue(LiveObserverConfigurationCheck.safe_start_allowed(result))
        self.assertNotIn("secret-ha", repr(result))
        self.assertNotIn("secret-esp", repr(result))

    def test_no_secret_leakage_from_process_environment(self):
        with patch.dict(os.environ, {"HA_TOKEN": "hidden-ha", "ESPHOME_API_KEY": "hidden-esp"}, clear=False):
            result = LiveObserverConfigurationCheck().check()
        text = repr(result)
        self.assertNotIn("hidden-ha", text)
        self.assertNotIn("hidden-esp", text)
        self.assertNotIn("token_value", text)

    def test_read_only_startup_contract(self):
        result = LiveObserverConfigurationCheck().check({"HA_TOKEN": "x", "ESPHOME_API_KEY": "y"})
        self.assertEqual("read-only", result.reader_mode)
        self.assertFalse(result.writes_allowed)
        self.assertEqual("deployment host / V2 service environment", result.execution_host)


if __name__ == "__main__":
    unittest.main()
