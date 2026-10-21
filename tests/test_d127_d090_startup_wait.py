import unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from node104_d090_transaction import SystemdService

class D127StartupWaitTests(unittest.TestCase):
    def test_delayed_polling_does_not_trigger_immediate_rollback(self):
        svc=object.__new__(SystemdService)
        svc.pinned=type('Pin',(),{'source_sha':'a','old_source_sha':'b'})()
        probe=iter((False,False,True))
        with patch.object(SystemdService,'_stable_process',side_effect=lambda sha:next(probe)), \
             patch.object(SystemdService,'active',return_value=True), \
             patch.object(SystemdService,'main_pid',return_value=21), \
             patch('node104_d090_transaction.time.sleep',return_value=None):
            self.assertTrue(svc.stable('a'))
    def test_exited_process_fails_without_waiting_all_timeout(self):
        svc=object.__new__(SystemdService)
        svc.pinned=type('Pin',(),{'source_sha':'a','old_source_sha':'b'})()
        with patch.object(SystemdService,'_stable_process',return_value=False), \
             patch.object(SystemdService,'active',return_value=False):
            self.assertFalse(svc.stable('a'))
