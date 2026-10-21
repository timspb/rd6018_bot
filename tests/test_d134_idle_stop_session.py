import unittest
from unittest.mock import Mock
from runtime.charge.lifecycle import stop_charge

class IdleStopSessionTests(unittest.TestCase):
    def test_explicit_clear_on_idle(self):
        host=Mock()
        host.STAGE_IDLE="Idle"
        host.current_stage="Idle"
        stop_charge(host,clear_session=True)
        host._clear_session_file.assert_called_once_with()
        self.assertEqual(host.current_stage,"Idle")

    def test_no_clear_when_preserving_on_idle(self):
        host=Mock()
        host.STAGE_IDLE="Idle"
        host.current_stage="Idle"
        stop_charge(host,clear_session=False)
        host._clear_session_file.assert_not_called()
