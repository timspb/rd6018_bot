import unittest

from protection_utils import should_delay_current_ramp
from protection_utils import should_use_startup_settle


class ProtectionUtilsTests(unittest.TestCase):
    def test_delay_when_current_rises_and_ocp_exists(self):
        self.assertTrue(should_delay_current_ramp(1.6, 0.22, 2.1, True))

    def test_no_delay_when_current_does_not_rise(self):
        self.assertFalse(should_delay_current_ramp(0.2, 0.22, 2.1, True))

    def test_no_delay_without_ocp(self):
        self.assertFalse(should_delay_current_ramp(1.6, 0.22, None, False))

    def test_startup_settle_on_turn_on_and_current_rise(self):
        self.assertTrue(should_use_startup_settle(1.6, 0.22, 2.6, True, True))

    def test_no_startup_settle_without_turn_on(self):
        self.assertFalse(should_use_startup_settle(1.6, 0.22, 2.6, True, False))


if __name__ == "__main__":
    unittest.main()
