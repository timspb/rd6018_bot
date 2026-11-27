import unittest
from runtime.charge.link_session_recovery import RecoveryRoute, RecoveryAction, RecoveryAuthorizationInput, authorize_recovery_action

class ColdStartRecoveryTests(unittest.TestCase):
    def test_live_runtime_wires_cold_start_before_every_recovery_action(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        runtime=(root/'runtime/production_runtime.py').read_text(encoding='utf-8')
        application=(root/'application/session_recovery_service.py').read_text(encoding='utf-8')
        self.assertIn('await SessionRecoveryService.run_cycle(',runtime)
        self.assertIn('cold_start = not getattr(',application)
        self.assertIn('mark_startup_observation_seen(controller)',application)
        self.assertNotIn('controller._d125_startup_observation_seen =',application)
        self.assertEqual(application.count('cold_start=cold_start'),3)

    def test_persisted_idle_cold_start_never_enables(self):
        x=RecoveryAuthorizationInput(route=RecoveryRoute.IDLE_LINK,restored=True,auto_enable_authorized=True,safe_wait=False,input_voltage_ok=True,cold_start=True)
        self.assertEqual(authorize_recovery_action(x),RecoveryAction.SKIP)
    def test_active_link_cold_start_never_enables(self):
        x=RecoveryAuthorizationInput(route=RecoveryRoute.ACTIVE_LINK,restored=True,auto_enable_authorized=True,safe_wait=False,input_voltage_ok=True,cold_start=True)
        self.assertEqual(authorize_recovery_action(x),RecoveryAction.SKIP)
